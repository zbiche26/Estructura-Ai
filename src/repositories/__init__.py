"""
Repositories Package

Este módulo centraliza todos los repositories para fácil importación.

Uso:
    from src.repositories import product_repo, sale_repo, conversation_repo
    
    # Usar directamente
    products = product_repo.get_all()
    sales = sale_repo.get_daily_report()
"""

from src.repositories.base import BaseRepository
from src.repositories.product_repository import ProductRepository, product_repo
from src.repositories.sale_repository import (
    SaleRepository, 
    SaleItemRepository,
    sale_repo, 
    sale_item_repo
)
from src.repositories.conversation_repository import (
    ConversationRepository,
    MessageRepository,
    conversation_repo,
    message_repo
)
from src.repositories.conversation_repo import ConversationRepo

# Exports
__all__ = [
    # Classes
    "BaseRepository",
    "ProductRepository",
    "SaleRepository",
    "SaleItemRepository",
    "ConversationRepository",
    "ConversationRepo",
    "MessageRepository",
    
    # Instances
    "product_repo",
    "sale_repo",
    "sale_item_repo",
    "conversation_repo",
    "message_repo",
]

