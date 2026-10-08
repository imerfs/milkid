"""
Advanced reporting system for MelkID
Generate comprehensive reports for administrators and staff
"""

from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
from decimal import Decimal
from .models import (
    ServiceRequest, Property, Payment, UserProfile, 
    PropertyAdvertisement, ViolationReport, Municipality
)

class ReportGenerator:
    """
    Generate various reports for MelkID system
    """
    
    def __init__(self):
        self.today = timezone.now().date()
        self.this_month_start = self.today.replace(day=1)
        self.last_month_start = (self.this_month_start - timedelta(days=1)).replace(day=1)
        self.this_year_start = self.today.replace(month=1, day=1)
    
    def generate_dashboard_stats(self, user=None) -> Dict[str, Any]:
        """
        Generate comprehensive dashboard statistics
        """
        stats = {
            'overview': self._get_overview_stats(user),
            'service_requests': self._get_service_request_stats(user),
            'properties': self._get_property_stats(user),
            'payments': self._get_payment_stats(user),
            'users': self._get_user_stats(user),
            'trends': self._get_trend_data(user),
            'generated_at': timezone.now(),
        }
        
        return stats
    
    def _get_overview_stats(self, user=None) -> Dict[str, Any]:
        """Get general overview statistics"""
        base_filter = self._get_base_filter(user)
        
        return {
            'total_users': UserProfile.objects.filter(**base_filter).count(),
            'active_users': UserProfile.objects.filter(
                **base_filter, 
                user__last_login__gte=timezone.now() - timedelta(days=30)
            ).count(),
            'total_properties': Property.objects.count(),
            'total_requests': ServiceRequest.objects.filter(**base_filter).count(),
            'pending_requests': ServiceRequest.objects.filter(
                **base_filter, 
                status='pending'
            ).count(),
            'total_payments': Payment.objects.filter(**base_filter).aggregate(
                total=Sum('amount')
            )['total'] or 0,
            'pending_payments': Payment.objects.filter(
                **base_filter, 
                status='pending'
            ).aggregate(
                total=Sum('amount')
            )['total'] or 0,
        }
    
    def _get_service_request_stats(self, user=None) -> Dict[str, Any]:
        """Get service request statistics"""
        base_filter = self._get_base_filter(user)
        
        # Status distribution
        status_stats = ServiceRequest.objects.filter(*