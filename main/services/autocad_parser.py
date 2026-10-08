"""
AutoCAD file parser service for extracting property information
"""
import ezdxf
import re
from decimal import Decimal
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

class AutoCADParser:
    """
    Parser class for extracting property information from AutoCAD files
    Supports both DXF and DWG formats (DWG needs conversion first)
    """
    
    def __init__(self, file_path: str):
        """
        Initialize parser with file path
        
        Args:
            file_path: Path to the DXF file
        """
        self.file_path = file_path
        self.doc = None
        self.extracted_data = {}
        
    def parse_file(self) -> Dict[str, Any]:
        """
        Main method to parse the DXF file and extract all information
        
        Returns:
            Dictionary containing extracted property data
        """
        try:
            # Load the DXF file
            self.doc = ezdxf.readfile(self.file_path)
            
            # Extract different types of information
            self.extracted_data = {
                'area': self.extract_area(),
                'street_width': self.extract_street_width(),
                'boundaries': self.extract_boundaries(),
                'raw_texts': self.extract_all_texts()  # For debugging and manual review
            }
            
            return self.extracted_data
            
        except ezdxf.DXFError as e:
            logger.error(f"Error reading DXF file: {str(e)}")
            raise Exception(f"خطا در خواندن فایل DXF: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error parsing file: {str(e)}")
            raise Exception(f"خطای غیرمنتظره در پردازش فایل: {str(e)}")
    
    def extract_all_texts(self) -> list:
        """
        Extract all text entities from the file for analysis
        
        Returns:
            List of all text content found in the file
        """
        texts = []
        
        if not self.doc:
            return texts
            
        # Get modelspace
        msp = self.doc.modelspace()
        
        # Extract TEXT entities
        for entity in msp.query('TEXT'):
            if hasattr(entity.dxf, 'text'):
                texts.append(entity.dxf.text)
        
        # Extract MTEXT entities (multiline text)
        for entity in msp.query('MTEXT'):
            if hasattr(entity, 'text'):
                # MTEXT might have formatting codes, clean them
                clean_text = self._clean_mtext(entity.text)
                texts.append(clean_text)
        
        # Extract ATTRIB and ATTDEF entities (block attributes)
        for entity in msp.query('ATTRIB ATTDEF'):
            if hasattr(entity.dxf, 'text'):
                texts.append(entity.dxf.text)
        
        return texts
    
    def _clean_mtext(self, text: str) -> str:
        """
        Clean MTEXT formatting codes
        
        Args:
            text: Raw MTEXT content
            
        Returns:
            Cleaned text without formatting codes
        """
        # Remove common MTEXT formatting codes
        clean = re.sub(r'\\[A-Z][^;]*;', '', text)  # Remove formatting like \C1;
        clean = re.sub(r'\\P', '\n', clean)  # Convert paragraph markers to newlines
        clean = re.sub(r'\\[\\{}]', '', clean)  # Remove escape sequences
        clean = re.sub(r'{\\[^}]*}', '', clean)  # Remove formatting groups
        
        return clean.strip()
    
    def extract_area(self) -> Optional[Decimal]:
        """
        Extract property area from text entities
        
        Returns:
            Area in square meters or None if not found
        """
        # Patterns for finding area in Persian and English
        patterns = [
            # Persian patterns
            r'مساحت\s*(?:زمین)?\s*(?:\(از شمیم\))?\s*[:؟]?\s*(\d+(?:\.\d+)?)\s*(?:متر\s*مربع|م2)',
            r'(\d+(?:\.\d+)?)\s*متر\s*مربع',
            r'مساحت\s*[:؟]?\s*(\d+(?:\.\d+)?)',
            
            # English patterns
            r'Area\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:m2|m²|sqm)',
            r'(\d+(?:\.\d+)?)\s*(?:m2|m²|square\s*meters?)',
        ]
        
        # Search in all extracted texts
        for text in self.extract_all_texts():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        area = Decimal(match.group(1))
                        logger.info(f"Found area: {area} m²")
                        return area
                    except:
                        continue
        
        logger.warning("Area not found in file")
        return None
    
    def extract_street_width(self) -> Optional[Decimal]:
        """
        Extract street/passage width from text entities
        
        Returns:
            Street width in meters or None if not found
        """
        patterns = [
            # Persian patterns
            r'متراژ\s*معبر\s*[:؟]?\s*(\d+(?:\.\d+)?)\s*(?:متر)?',
            r'عرض\s*معبر\s*[:؟]?\s*(\d+(?:\.\d+)?)\s*(?:متر)?',
            r'معبر\s*(\d+(?:\.\d+)?)\s*متر',
            r'کوچه\s*(\d+(?:\.\d+)?)\s*متری',
            
            # English patterns
            r'Street\s*width\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:m|meters?)?',
            r'Passage\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:m|meters?)?',
        ]
        
        for text in self.extract_all_texts():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        width = Decimal(match.group(1))
                        logger.info(f"Found street width: {width} m")
                        return width
                    except:
                        continue
        
        logger.warning("Street width not found in file")
        return None
    
    def extract_boundaries(self) -> Dict[str, Dict[str, Any]]:
        """
        Extract property boundaries (north, south, east, west)
        
        Returns:
            Dictionary with boundary information for each direction
        """
        boundaries = {
            'north': {'length': None, 'boundary': None},
            'south': {'length': None, 'boundary': None},
            'east': {'length': None, 'boundary': None},
            'west': {'length': None, 'boundary': None}
        }
        
        # Direction patterns in Persian
        direction_patterns = {
            'north': [
                r'شمال[اً]?\s*[:؟]?\s*به\s*طول\s*(\d+(?:\.\d+)?)\s*متر\s*(?:به\s+)?(.+?)(?:،|؛|$)',
                r'شمال[اً]?\s*[:؟]?\s*(\d+(?:\.\d+)?)\s*متر\s*(?:به\s+)?(.+?)(?:،|؛|$)',
            ],
            'south': [
                r'جنوب[اً]?\s*[:؟]?\s*به\s*طول\s*(\d+(?:\.\d+)?)\s*متر\s*(?:به\s+)?(.+?)(?:،|؛|$)',
                r'جنوب[اً]?\s*[:؟]?\s*(\d+(?:\.\d+)?)\s*متر\s*(?:به\s+)?(.+?)(?:،|؛|$)',
            ],
            'east': [
                r'شرق[اً]?\s*[:؟]?\s*به\s*طول\s*(\d+(?:\.\d+)?)\s*متر\s*(?:به\s+)?(.+?)(?:،|؛|$)',
                r'شرق[اً]?\s*[:؟]?\s*(\d+(?:\.\d+)?)\s*متر\s*(?:به\s+)?(.+?)(?:،|؛|$)',
            ],
            'west': [
                r'غرب[اً]?\s*[:؟]?\s*به\s*طول\s*(\d+(?:\.\d+)?)\s*متر\s*(?:به\s+)?(.+?)(?:،|؛|$)',
                r'غرب[اً]?\s*[:؟]?\s*(\d+(?:\.\d+)?)\s*متر\s*(?:به\s+)?(.+?)(?:،|؛|$)',
            ]
        }
        
        # Search in all texts
        all_texts = self.extract_all_texts()
        
        # Join all texts to search across line breaks
        full_text = ' '.join(all_texts)
        
        for direction, patterns in direction_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, full_text, re.IGNORECASE | re.MULTILINE)
                if match:
                    try:
                        length = Decimal(match.group(1))
                        boundary = match.group(2).strip()
                        
                        # Clean up the boundary text
                        boundary = re.sub(r'\s+', ' ', boundary)  # Normalize whitespace
                        boundary = boundary.rstrip('،؛,;.')  # Remove trailing punctuation
                        
                        boundaries[direction]['length'] = length
                        boundaries[direction]['boundary'] = boundary
                        
                        logger.info(f"Found {direction} boundary: {length}m to {boundary}")
                        break
                    except:
                        continue
        
        # Also look for simpler patterns without length
        simple_patterns = {
            'north': r'شمال[اً]?\s*[:؟]?\s*(?:به\s+)?(.+?)(?:،|؛|$)',
            'south': r'جنوب[اً]?\s*[:؟]?\s*(?:به\s+)?(.+?)(?:،|؛|$)',
            'east': r'شرق[اً]?\s*[:؟]?\s*(?:به\s+)?(.+?)(?:،|؛|$)',
            'west': r'غرب[اً]?\s*[:؟]?\s*(?:به\s+)?(.+?)(?:،|؛|$)',
        }
        
        for direction, pattern in simple_patterns.items():
            if boundaries[direction]['boundary'] is None:  # Only if not already found
                match = re.search(pattern, full_text, re.IGNORECASE | re.MULTILINE)
                if match:
                    boundary = match.group(1).strip()
                    boundary = re.sub(r'\s+', ' ', boundary)
                    boundary = boundary.rstrip('،؛,;.')
                    
                    # Don't overwrite if it contains another direction keyword
                    if not any(d in boundary.lower() for d in ['شمال', 'جنوب', 'شرق', 'غرب']):
                        boundaries[direction]['boundary'] = boundary
                        logger.info(f"Found {direction} boundary (no length): {boundary}")
        
        return boundaries
    
    def get_formatted_output(self) -> str:
        """
        Get formatted output for display
        
        Returns:
            Formatted string with extracted information
        """
        if not self.extracted_data:
            return "داده‌ای استخراج نشده است"
        
        output = []
        
        # Area
        if self.extracted_data.get('area'):
            output.append(f"مساحت زمین: {self.extracted_data['area']} متر مربع")
        
        # Street width
        if self.extracted_data.get('street_width'):
            output.append(f"متراژ معبر: {self.extracted_data['street_width']} متر")
        
        # Boundaries
        boundaries = self.extracted_data.get('boundaries', {})
        
        if boundaries.get('north'):
            north = boundaries['north']
            if north['length'] and north['boundary']:
                output.append(f"شمالاً: به طول {north['length']} متر به {north['boundary']}")
            elif north['boundary']:
                output.append(f"شمالاً: به {north['boundary']}")
        
        if boundaries.get('south'):
            south = boundaries['south']
            if south['length'] and south['boundary']:
                output.append(f"جنوباً: به طول {south['length']} متر به {south['boundary']}")
            elif south['boundary']:
                output.append(f"جنوباً: به {south['boundary']}")
        
        if boundaries.get('east'):
            east = boundaries['east']
            if east['length'] and east['boundary']:
                output.append(f"شرقاً: به طول {east['length']} متر به {east['boundary']}")
            elif east['boundary']:
                output.append(f"شرقاً: به {east['boundary']}")
        
        if boundaries.get('west'):
            west = boundaries['west']
            if west['length'] and west['boundary']:
                output.append(f"غرباً: به طول {west['length']} متر به {west['boundary']}")
            elif west['boundary']:
                output.append(f"غرباً: به {west['boundary']}")
        
        return '\n'.join(output) if output else "اطلاعاتی یافت نشد"