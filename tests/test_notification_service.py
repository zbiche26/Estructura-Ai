"""Tests de NotificationService"""

import pytest
from unittest.mock import Mock, patch
from src.services.notification_service import NotificationService


@pytest.fixture
def notification_service():
    return NotificationService()


def test_notification_service_init(notification_service):
    """Test: Servicio se inicializa"""
    assert notification_service is not None


@patch('smtplib.SMTP')
def test_send_email_alert(mock_smtp, notification_service):
    """Test: Enviar email (mock)"""
    notification_service.smtp_user = 'test@test.com'
    notification_service.smtp_password = 'password'
    
    alert_data = {
        'product_name': 'Laptop HP',
        'current_stock': 3,
        'threshold': 10,
        'severity': 'critical',
        'category': 'Tecnología'
    }
    
    result = notification_service.send_email_alert(alert_data, 'admin@test.com')
    
    assert mock_smtp.called


@patch('requests.post')
def test_send_webhook(mock_post, notification_service):
    """Test: Enviar webhook"""
    notification_service.webhook_url = 'https://example.com/webhook'
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response
    
    alert_data = {
        'product_id': '123',
        'product_name': 'Laptop HP',
        'current_stock': 3,
        'threshold': 10,
        'severity': 'critical'
    }
    
    result = notification_service.send_webhook(alert_data)
    
    assert result is True
    assert mock_post.called