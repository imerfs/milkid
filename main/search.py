"""
Advanced search functionality for MelkID
Provides fast and accurate search across all models
"""

from django.db.models import Q, Count
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.conf import settings
import re
from typing import List, Dict, Any, Optional
from .models import (
    Property, ServiceRequest, UserProfile, 
    PropertyAdvertisement, Municipality, Payment
)

class AdvancedSearch:
    """
    Advanced search engine for MelkID with Persian support
    """
    
    def __init__(self):
        self.use_postgres = 'postgresql' in settings.DATABASES['default']['ENGINE']
    
    def search_all(self, query: str, user=None, limit: int = 50) -> Dict[str, Any]:
        """
        Search across all models and return categorized results
        """
        if not query or len(query.strip()) < 2:
            return self._empty_results()
        
        query = query.strip()
        results = {
            'properties': self.search_properties(query, limit=10),
            'service_requests': self.search_service_requests(query, user, limit=10),
            'users': self.search_users(query, user, limit=10),
            'advertisements': self.search_advertisements(query, limit=10),
            'payments': self.search_payments(query, user, limit=10),
            'total_count': 0,
            'query': query,
        }
        
        # Calculate total count
        results['total_count'] = sum([
            len(results['properties']),
            len(results['service_requests']),
            len(results['users']),
            len(results['advertisements']),
            len(results['payments']),
        ])
        
        return results
    
    def search_properties(self, query: str, limit: int = 20) -> List[Property]:
        """
        Search properties by address, owner name, parcel number, etc.
        """
        if self.use_postgres:
            return self._search_properties_postgres(query, limit)
        else:
            return self._search_properties_basic(query, limit)
    
    def _search_properties_postgres(self, query: str, limit: int) -> List[Property]:
        """PostgreSQL full-text search for properties"""
        search_vector = SearchVector('address', 'owner_name', 'parcel_number', 'deed_number')
        search_query = SearchQuery(query)
        
        return Property.objects.annotate(
            search=search_vector,
            rank=SearchRank(search_vector, search_query)
        ).filter(
            search=search_query
        ).order_by('-rank', '-created_at')[:limit]
    
    def _search_properties_basic(self, query: str, limit: int) -> List[Property]:
        """Basic search for SQLite and other databases"""
        # Clean and prepare query
        terms = self._prepare_search_terms(query)
        
        q_objects = Q()
        for term in terms:
            q_objects |= (
                Q(address__icontains=term) |
                Q(owner_name__icontains=term) |
                Q(parcel_number__icontains=term) |
                Q(deed_number__icontains=term) |
                Q(location_area__icontains=term)
            )
        
        return Property.objects.filter(q_objects).distinct()[:limit]
    
    def search_service_requests(self, query: str, user=None, limit: int = 20) -> List[ServiceRequest]:
        """
        Search service requests by title, description, parcel number
        """
        terms = self._prepare_search_terms(query)
        
        q_objects = Q()
        for term in terms:
            q_objects |= (
                Q(title__icontains=term) |
                Q(description__icontains=term) |
                Q(parcel_number__icontains=term) |
                Q(property_address__icontains=term)
            )
        
        queryset = ServiceRequest.objects.filter(q_objects)
        
        # Filter by user permissions
        if user and not user.profile.is_staff_member():
            queryset = queryset.filter(user=user)
        
        return queryset.select_related('user', 'service').distinct()[:limit]
    
    def search_users(self, query: str, requesting_user=None, limit: int = 20) -> List[UserProfile]:
        """
        Search users by name, national ID, mobile (with permission checks)
        """
        # Only staff members can search other users
        if not requesting_user or not requesting_user.profile.is_staff_member():
            return []
        
        terms = self._prepare_search_terms(query)
        
        q_objects = Q()
        for term in terms:
            q_objects |= (
                Q(user__first_name__icontains=term) |
                Q(user__last_name__icontains=term) |
                Q(national_id__icontains=term) |
                Q(mobile_number__icontains=term) |
                Q(city_village__icontains=term)
            )
        
        return UserProfile.objects.filter(q_objects).select_related('user').distinct()[:limit]
    
    def search_advertisements(self, query: str, limit: int = 20) -> List[PropertyAdvertisement]:
        """
        Search property advertisements
        """
        terms = self._prepare_search_terms(query)
        
        q_objects = Q()
        for term in terms:
            q_objects |= (
                Q(description__icontains=term) |
                Q(address__icontains=term) |
                Q(city_village__icontains=term) |
                Q(contact_name__icontains=term)
            )
        
        return PropertyAdvertisement.objects.filter(
            q_objects,
            status='approved'
        ).select_related('user').distinct()[:limit]
    
    def search_payments(self, query: str, user=None, limit: int = 20) -> List[Payment]:
        """
        Search payments by receipt number, description
        """
        terms = self._prepare_search_terms(query)
        
        q_objects = Q()
        for term in terms:
            q_objects |= (
                Q(receipt_number__icontains=term) |
                Q(description__icontains=term)
            )
        
        queryset = Payment.objects.filter(q_objects)
        
        # Filter by user permissions
        if user and not user.profile.is_staff_member():
            queryset = queryset.filter(user=user)
        
        return queryset.select_related('user', 'property').distinct()[:limit]
    
    def smart_search(self, query: str, user=None) -> Dict[str, Any]:
        """
        Intelligent search that detects query type and provides targeted results
        """
        query = query.strip()
        
        # Detect query patterns
        search_type = self._detect_search_type(query)
        
        if search_type == 'national_id':
            return self._search_by_national_id(query, user)
        elif search_type == 'mobile':
            return self._search_by_mobile(query, user)
        elif search_type == 'parcel_number':
            return self._search_by_parcel_number(query)
        elif search_type == 'receipt_number':
            return self._search_by_receipt_number(query, user)
        else:
            return self.search_all(query, user)
    
    def _detect_search_type(self, query: str) -> str:
        """
        Detect the type of search query based on patterns
        """
        # Remove spaces and dashes
        clean_query = re.sub(r'[\s\-]', '', query)
        
        # National ID pattern (10 digits)
        if re.match(r'^\d{10}$', clean_query):
            return 'national_id'
        
        # Mobile number pattern (11 digits starting with 09)
        if re.match(r'^09\d{9}$', clean_query):
            return 'mobile'
        
        # Parcel number patterns
        if re.match(r'^\d+[\/\-]?\d*$', query):
            return 'parcel_number'
        
        # Receipt number pattern
        if re.match(r'^[A-Z0-9\-]+$', query.upper()):
            return 'receipt_number'
        
        return 'general'
    
    def _search_by_national_id(self, national_id: str, user=None) -> Dict[str, Any]:
        """Search by national ID"""
        results = {'type': 'national_id', 'query': national_id}
        
        # Find user
        try:
            profile = UserProfile.objects.select_related('user').get(national_id=national_id)
            results['user'] = profile
            
            # Find related data
            results['properties'] = Property.objects.filter(owner_national_id=national_id)[:10]
            results['service_requests'] = ServiceRequest.objects.filter(user=profile.user)[:10]
            results['payments'] = Payment.objects.filter(user=profile.user)[:10]
            
        except UserProfile.DoesNotExist:
            # Search in properties even if user doesn't exist
            results['properties'] = Property.objects.filter(owner_national_id=national_id)[:10]
            results['user'] = None
            results['service_requests'] = []
            results['payments'] = []
        
        return results
    
    def _search_by_mobile(self, mobile: str, user=None) -> Dict[str, Any]:
        """Search by mobile number"""
        if not user or not user.profile.is_staff_member():
            return {'error': 'دسترسی محدود'}
        
        results = {'type': 'mobile', 'query': mobile}
        
        try:
            profile = UserProfile.objects.select_related('user').get(mobile_number=mobile)
            results['user'] = profile
            results['properties'] = Property.objects.filter(owner_phone=mobile)[:10]
        except UserProfile.DoesNotExist:
            results['user'] = None
            results['properties'] = Property.objects.filter(owner_phone=mobile)[:10]
        
        return results
    
    def _search_by_parcel_number(self, parcel: str) -> Dict[str, Any]:
        """Search by parcel number"""
        results = {'type': 'parcel_number', 'query': parcel}
        
        # Try exact match first
        properties = Property.objects.filter(parcel_number=parcel)
        
        if not properties.exists():
            # Try partial match
            properties = Property.objects.filter(parcel_number__icontains=parcel)
        
        results['properties'] = properties[:10]
        
        # Find related service requests
        if properties.exists():
            property_obj = properties.first()
            results['service_requests'] = ServiceRequest.objects.filter(
                Q(parcel_number=parcel) | Q(user=property_obj.created_by)
            )[:10]
        
        return results
    
    def _search_by_receipt_number(self, receipt: str, user=None) -> Dict[str, Any]:
        """Search by receipt number"""
        results = {'type': 'receipt_number', 'query': receipt}
        
        payments = Payment.objects.filter(receipt_number__icontains=receipt)
        
        # Filter by user permissions
        if user and not user.profile.is_staff_member():
            payments = payments.filter(user=user)
        
        results['payments'] = payments[:10]
        
        return results
    
    def _prepare_search_terms(self, query: str) -> List[str]:
        """
        Prepare search terms by cleaning and splitting
        """
        # Remove extra spaces and split
        terms = query.strip().split()
        
        # Remove very short terms (less than 2 characters)
        terms = [term for term in terms if len(term) >= 2]
        
        # Add the full query as well
        if len(query.strip()) >= 2:
            terms.append(query.strip())
        
        return terms
    
    def _empty_results(self) -> Dict[str, Any]:
        """Return empty search results structure"""
        return {
            'properties': [],
            'service_requests': [],
            'users': [],
            'advertisements': [],
            'payments': [],
            'total_count': 0,
            'query': '',
        }
    
    def get_search_suggestions(self, query: str, limit: int = 5) -> List[str]:
        """
        Get search suggestions based on partial query
        """
        if len(query) < 2:
            return []
        
        suggestions = set()
        
        # Get suggestions from property addresses
        properties = Property.objects.filter(
            address__icontains=query
        ).values_list('address', flat=True)[:limit]
        
        for address in properties:
            # Extract relevant parts of the address
            words = address.split()
            for word in words:
                if query.lower() in word.lower() and len(word) > 2:
                    suggestions.add(word)
        
        # Get suggestions from city/village names
        cities = UserProfile.objects.filter(
            city_village__icontains=query
        ).values_list('city_village', flat=True).distinct()[:limit]
        
        suggestions.update(cities)
        
        return list(suggestions)[:limit]

# Global search instance
search_engine = AdvancedSearch()