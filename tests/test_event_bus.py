"""
Tests para Event Bus
====================

Tests automatizados que verifican que el sistema de eventos
funciona correctamente en diferentes escenarios.

Ejecutar: python -m pytest tests/test_event_bus.py -v
"""

import pytest
import time
from src.core.event_bus import Event, EventBus, event_handler
from src.core.tenant_context import TenantContext, TenantContextManager


# ============================================
# TESTS DE EVENT
# ============================================

class TestEvent:
    """Tests para la clase Event"""
    
    def test_crear_event_basico(self):
        """Test: Crear un evento básico"""
        event = Event(
            event_type="test_event",
            data={"mensaje": "hola"},
            tenant_id="test-123"
        )
        
        assert event.event_type == "test_event"
        assert event.data["mensaje"] == "hola"
        assert event.tenant_id == "test-123"
        assert event.event_id is not None
        assert event.timestamp is not None
    
    def test_event_tiene_id_unico(self):
        """Test: Cada evento tiene un ID único"""
        event1 = Event(event_type="test", data={}, tenant_id="test-123")
        event2 = Event(event_type="test", data={}, tenant_id="test-123")
        
        assert event1.event_id != event2.event_id
    
    def test_event_con_metadata(self):
        """Test: Evento puede tener metadata adicional"""
        event = Event(
            event_type="test",
            data={"dato": "valor"},
            tenant_id="test-123",
            metadata={"source": "api", "version": "1.0"}
        )
        
        assert event.metadata["source"] == "api"
        assert event.metadata["version"] == "1.0"


# ============================================
# TESTS DE EVENT BUS
# ============================================

class TestEventBus:
    """Tests para la clase EventBus"""
    
    def setup_method(self):
        """Se ejecuta antes de cada test"""
        self.event_bus = EventBus()
        
        # Establecer tenant de prueba
        self.tenant = TenantContext(
            tenant_id="test-tenant",
            tenant_name="Test Company",
            plan="pro"
        )
        TenantContextManager.set_current(self.tenant)
    
    def teardown_method(self):
        """Se ejecuta después de cada test"""
        TenantContextManager.clear()
    
    def test_subscribe_y_publish(self):
        """Test: Suscribir y publicar evento básico"""
        # Variable para capturar el evento
        eventos_recibidos = []
        
        def handler(event: Event):
            eventos_recibidos.append(event)
        
        # Suscribir
        self.event_bus.subscribe("test_event", handler)
        
        # Publicar
        self.event_bus.publish("test_event", {"mensaje": "hola"})
        
        # Verificar
        assert len(eventos_recibidos) == 1
        assert eventos_recibidos[0].event_type == "test_event"
        assert eventos_recibidos[0].data["mensaje"] == "hola"
    
    def test_multiples_suscriptores(self):
        """Test: Múltiples suscriptores reciben el mismo evento"""
        contador_1 = {"count": 0}
        contador_2 = {"count": 0}
        
        def handler_1(event: Event):
            contador_1["count"] += 1
        
        def handler_2(event: Event):
            contador_2["count"] += 1
        
        # Suscribir ambos handlers
        self.event_bus.subscribe("test_event", handler_1)
        self.event_bus.subscribe("test_event", handler_2)
        
        # Publicar
        self.event_bus.publish("test_event", {})
        
        # Verificar que ambos se ejecutaron
        assert contador_1["count"] == 1
        assert contador_2["count"] == 1
    
    def test_evento_sin_suscriptores(self):
        """Test: Publicar evento sin suscriptores no causa error"""
        # No debería lanzar excepción
        self.event_bus.publish("evento_sin_suscriptores", {"dato": "valor"})
        
        # Verificar que se guardó en historial
        history = self.event_bus.get_history("evento_sin_suscriptores")
        assert len(history) == 1
    
    def test_unsubscribe(self):
        """Test: Desuscribir un handler"""
        contador = {"count": 0}
        
        def handler(event: Event):
            contador["count"] += 1
        
        # Suscribir
        self.event_bus.subscribe("test_event", handler)
        
        # Publicar (debería ejecutarse)
        self.event_bus.publish("test_event", {})
        assert contador["count"] == 1
        
        # Desuscribir
        self.event_bus.unsubscribe("test_event", handler)
        
        # Publicar de nuevo (NO debería ejecutarse)
        self.event_bus.publish("test_event", {})
        assert contador["count"] == 1  # Sigue en 1
    
    def test_handler_con_error_no_detiene_otros(self):
        """Test: Si un handler falla, los demás siguen ejecutándose"""
        contador_ok = {"count": 0}
        
        def handler_que_falla(event: Event):
            raise ValueError("Error intencional")
        
        def handler_ok(event: Event):
            contador_ok["count"] += 1
        
        # Suscribir ambos
        self.event_bus.subscribe("test_event", handler_que_falla)
        self.event_bus.subscribe("test_event", handler_ok)
        
        # Publicar
        self.event_bus.publish("test_event", {})
        
        # El handler_ok debe haberse ejecutado a pesar del error
        assert contador_ok["count"] == 1
    
    def test_get_history(self):
        """Test: Obtener historial de eventos"""
        # Publicar varios eventos
        self.event_bus.publish("event_1", {"id": 1})
        self.event_bus.publish("event_2", {"id": 2})
        self.event_bus.publish("event_1", {"id": 3})
        
        # Obtener todo el historial
        all_history = self.event_bus.get_history()
        assert len(all_history) == 3
        
        # Filtrar por tipo
        event_1_history = self.event_bus.get_history(event_type="event_1")
        assert len(event_1_history) == 2
        
        event_2_history = self.event_bus.get_history(event_type="event_2")
        assert len(event_2_history) == 1
    
    def test_get_history_por_tenant(self):
        """Test: Filtrar historial por tenant"""
        # Publicar evento con tenant actual
        self.event_bus.publish("test_event", {"tenant": "test-tenant"})
        
        # Cambiar tenant
        otro_tenant = TenantContext(
            tenant_id="otro-tenant",
            tenant_name="Otra Empresa",
            plan="free"
        )
        TenantContextManager.clear()
        TenantContextManager.set_current(otro_tenant)
        
        # Publicar con otro tenant
        self.event_bus.publish("test_event", {"tenant": "otro-tenant"})
        
        # Filtrar por tenant original
        history_tenant_1 = self.event_bus.get_history(tenant_id="test-tenant")
        assert len(history_tenant_1) == 1
        assert history_tenant_1[0].tenant_id == "test-tenant"
        
        # Filtrar por segundo tenant
        history_tenant_2 = self.event_bus.get_history(tenant_id="otro-tenant")
        assert len(history_tenant_2) == 1
        assert history_tenant_2[0].tenant_id == "otro-tenant"
    
    def test_get_subscribers_count(self):
        """Test: Contar suscriptores de un evento"""
        def handler_1(event): pass
        def handler_2(event): pass
        def handler_3(event): pass
        
        # Sin suscriptores
        assert self.event_bus.get_subscribers_count("test_event") == 0
        
        # Con 1 suscriptor
        self.event_bus.subscribe("test_event", handler_1)
        assert self.event_bus.get_subscribers_count("test_event") == 1
        
        # Con 3 suscriptores
        self.event_bus.subscribe("test_event", handler_2)
        self.event_bus.subscribe("test_event", handler_3)
        assert self.event_bus.get_subscribers_count("test_event") == 3
    
    def test_get_all_event_types(self):
        """Test: Obtener todos los tipos de eventos con suscriptores"""
        def handler(event): pass
        
        # Sin suscriptores
        assert len(self.event_bus.get_all_event_types()) == 0
        
        # Con suscriptores
        self.event_bus.subscribe("event_1", handler)
        self.event_bus.subscribe("event_2", handler)
        self.event_bus.subscribe("event_3", handler)
        
        event_types = self.event_bus.get_all_event_types()
        assert len(event_types) == 3
        assert "event_1" in event_types
        assert "event_2" in event_types
        assert "event_3" in event_types
    
    def test_clear_history(self):
        """Test: Limpiar historial de eventos"""
        # Publicar eventos
        self.event_bus.publish("test_event", {})
        self.event_bus.publish("test_event", {})
        
        # Verificar que hay historial
        assert len(self.event_bus.get_history()) == 2
        
        # Limpiar
        self.event_bus.clear_history()
        
        # Verificar que se limpió
        assert len(self.event_bus.get_history()) == 0
    
    def test_clear_subscribers(self):
        """Test: Limpiar suscriptores"""
        def handler(event): pass
        
        # Suscribir a varios eventos
        self.event_bus.subscribe("event_1", handler)
        self.event_bus.subscribe("event_2", handler)
        
        assert self.event_bus.get_subscribers_count("event_1") == 1
        assert self.event_bus.get_subscribers_count("event_2") == 1
        
        # Limpiar solo event_1
        self.event_bus.clear_subscribers("event_1")
        assert self.event_bus.get_subscribers_count("event_1") == 0
        assert self.event_bus.get_subscribers_count("event_2") == 1
        
        # Limpiar todos
        self.event_bus.clear_subscribers()
        assert self.event_bus.get_subscribers_count("event_2") == 0


# ============================================
# TESTS DEL DECORADOR
# ============================================

class TestEventHandlerDecorator:
    """Tests para el decorador @event_handler"""
    
    def test_decorador_agrega_metadata(self):
        """Test: Decorador agrega metadata a la función"""
        
        @event_handler("test_event")
        def mi_handler(event: Event):
            pass
        
        assert hasattr(mi_handler, '_is_event_handler')
        assert mi_handler._is_event_handler == True
        assert mi_handler._event_type == "test_event"
    
    def test_decorador_no_afecta_funcionalidad(self):
        """Test: Decorador no afecta la ejecución de la función"""
        
        @event_handler("test_event")
        def mi_handler(event: Event):
            return f"Procesado: {event.data}"
        
        # Crear evento de prueba
        event = Event(
            event_type="test_event",
            data={"mensaje": "hola"},
            tenant_id="test-123"
        )
        
        # Ejecutar función
        resultado = mi_handler(event)
        assert resultado == "Procesado: {'mensaje': 'hola'}"


# ============================================
# TESTS DE INTEGRACIÓN
# ============================================

class TestEventBusIntegration:
    """Tests de integración del Event Bus con otros componentes"""
    
    def setup_method(self):
        """Setup para cada test"""
        self.event_bus = EventBus()
        
        self.tenant = TenantContext(
            tenant_id="integration-test",
            tenant_name="Integration Test",
            plan="pro"
        )
        TenantContextManager.set_current(self.tenant)
    
    def teardown_method(self):
        """Cleanup después de cada test"""
        TenantContextManager.clear()
    
    def test_flujo_completo_venta(self):
        """Test: Flujo completo de una venta con eventos"""
        # Simular diferentes componentes del sistema
        acciones_realizadas = []
        
        # Handler: Actualizar inventario
        def actualizar_inventario(event: Event):
            producto_id = event.data["producto_id"]
            cantidad = event.data["cantidad"]
            acciones_realizadas.append(f"inventario_actualizado:{producto_id}:{cantidad}")
        
        # Handler: Actualizar BD vectorial
        def actualizar_vectorial(event: Event):
            producto_id = event.data["producto_id"]
            acciones_realizadas.append(f"vectorial_actualizado:{producto_id}")
        
        # Handler: Notificar por WhatsApp
        def notificar_whatsapp(event: Event):
            acciones_realizadas.append("whatsapp_enviado")
        
        # Handler: Registrar en analytics
        def registrar_analytics(event: Event):
            acciones_realizadas.append("analytics_registrado")
        
        # Suscribir todos los handlers
        self.event_bus.subscribe("venta_realizada", actualizar_inventario)
        self.event_bus.subscribe("venta_realizada", actualizar_vectorial)
        self.event_bus.subscribe("venta_realizada", notificar_whatsapp)
        self.event_bus.subscribe("venta_realizada", registrar_analytics)
        
        # Publicar evento de venta
        self.event_bus.publish("venta_realizada", {
            "producto_id": "PROD-123",
            "cantidad": 3,
            "precio_total": 2550.00
        })
        
        # Verificar que todas las acciones se ejecutaron
        assert len(acciones_realizadas) == 4
        assert "inventario_actualizado:PROD-123:3" in acciones_realizadas
        assert "vectorial_actualizado:PROD-123" in acciones_realizadas
        assert "whatsapp_enviado" in acciones_realizadas
        assert "analytics_registrado" in acciones_realizadas


# ============================================
# EJECUTAR TESTS
# ============================================

if __name__ == "__main__":
    """Ejecutar tests directamente"""
    pytest.main([__file__, "-v", "--tb=short"])