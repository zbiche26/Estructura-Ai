from typing import Optional
from loguru import logger

from src.plugins.base import BasePlugin, PluginMetadata
from src.services.stock_manager import StockManager


class InventoryPlugin(BasePlugin):
    """
    Plugin de gestiÃ³n de inventario.

    Responsabilidades:
    - Gestionar stock de productos
    - Reservar stock durante conversaciones
    - Liberar reservas expiradas
    - Exponer servicios de inventario al sistema
    """

    name = "inventory_plugin"
    version = "1.0.0"
    description = "GestiÃ³n de inventario, reservas de stock y alertas"

    def __init__(self, event_bus, db_client=None, **kwargs):
        super().__init__(event_bus)
        
        # Define metadata
        self._metadata = PluginMetadata(
            name=self.name,
            version=self.version,
            description=self.description,
            author="Cristian LÃ³pez",
            dependencies=[],
            tenant_specific=True
        )

        self.db_client = db_client
        self.stock_manager: Optional[StockManager] = None
        self._running = False

    # ---------------------------------------------------------
    # Plugin Lifecycle
    # ---------------------------------------------------------

    def on_initialize(self):
        """
        InicializaciÃ³n del plugin.
        """
        logger.info("Inicializando InventoryPlugin...")

        self.stock_manager = StockManager()

        logger.success("InventoryPlugin inicializado")

    def on_start(self):
        """
        Se ejecuta cuando el sistema levanta el plugin.
        """
        logger.info("Iniciando InventoryPlugin...")

        self._running = True

        # Suscribirse a eventos relevantes
        self.event_bus.subscribe("conversation.started", self._handle_conversation_started)
        self.event_bus.subscribe("purchase.completed", self._handle_purchase_completed)

        logger.success("InventoryPlugin iniciado")

    def on_stop(self):
        """
        Se ejecuta cuando el sistema se apaga.
        """
        logger.info("Deteniendo InventoryPlugin...")

        self._running = False

        logger.success("InventoryPlugin detenido")

    # ---------------------------------------------------------
    # Event Handlers
    # ---------------------------------------------------------

    def _handle_conversation_started(self, event):
        """
        Evento cuando inicia una conversaciÃ³n.
        """
        logger.debug(f"Conversation started: {event}")

    def _handle_purchase_completed(self, event):
        """
        Evento cuando se completa una compra.
        """
        logger.debug(f"Purchase completed: {event}")

    # ---------------------------------------------------------
    # Public API del plugin
    # ---------------------------------------------------------

    def get_stock_manager(self) -> StockManager:
        """
        Permite a otros componentes acceder al StockManager.
        """
        if not self.stock_manager:
            raise RuntimeError("StockManager no inicializado")

        return self.stock_manager

    def check_inventory(self, **kwargs):
        return {'status': 'ok', 'items': [], 'alerts': []}

    def analyze_trends(self, **kwargs):
        return {'trends': [], 'status': 'ok'}

