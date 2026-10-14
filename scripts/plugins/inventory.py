# src/plugins/inventory.py
from src.core.plugin_registry import register_plugin
from src.repositories.product_repository import ProductRepository  # Extendemos para stock

class InventoryPlugin:
    def __init__(self, repo: ProductRepository):
        self.repo = repo

    def update_stock(self, product_id: str, quantity: int):
        return self.repo.update_stock(product_id, quantity)

    def reserve_stock(self, product_id: str, quantity: int, conversation_id: str):
        return self.repo.reserve_stock(product_id, quantity, conversation_id)

    def release_stock(self, reservation_id: str):
        return self.repo.release_stock(reservation_id)

    def get_stock_level(self, product_id: str):
        return self.repo.get_stock_level(product_id)

# Registrar (en init o app startup)
register_plugin('inventory', InventoryPlugin)