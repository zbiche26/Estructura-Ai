"""
Tests para TenantContext
========================

Tests automatizados que verifican que el sistema Multi-Tenant
funciona correctamente en diferentes escenarios.

Ejecutar: python -m pytest tests/test_tenant_context.py -v
"""

import pytest
from src.core.tenant_context import (
    TenantContext, 
    TenantContextManager,
    require_tenant
)


# ============================================
# TESTS DE TENANTCONTEXT
# ============================================

class TestTenantContext:
    """Tests para la clase TenantContext"""
    
    def test_crear_tenant_basico(self):
        """Test: Crear un tenant con datos básicos"""
        tenant = TenantContext(
            tenant_id="test-123",
            tenant_name="Test Company",
            plan="free"
        )
        
        assert tenant.tenant_id == "test-123"
        assert tenant.tenant_name == "Test Company"
        assert tenant.plan == "free"
        assert tenant.features_enabled == []
        assert tenant.config == {}
    
    def test_crear_tenant_completo(self):
        """Test: Crear un tenant con todos los datos"""
        tenant = TenantContext(
            tenant_id="test-456",
            tenant_name="Complete Company",
            plan="pro",
            features_enabled=["ai_agent", "analytics"],
            config={"max_products": 500}
        )
        
        assert tenant.tenant_id == "test-456"
        assert tenant.tenant_name == "Complete Company"
        assert tenant.plan == "pro"
        assert len(tenant.features_enabled) == 2
        assert tenant.config["max_products"] == 500
    
    def test_has_feature(self):
        """Test: Verificar si tenant tiene una feature"""
        tenant = TenantContext(
            tenant_id="test-789",
            tenant_name="Feature Test",
            plan="enterprise",
            features_enabled=["ai_agent", "excel_import"]
        )
        
        assert tenant.has_feature("ai_agent") == True
        assert tenant.has_feature("excel_import") == True
        assert tenant.has_feature("whatsapp") == False
    
    def test_get_config(self):
        """Test: Obtener valores de configuración"""
        tenant = TenantContext(
            tenant_id="test-101",
            tenant_name="Config Test",
            plan="pro",
            config={"max_products": 1000, "llm_model": "gpt-4"}
        )
        
        assert tenant.get_config("max_products") == 1000
        assert tenant.get_config("llm_model") == "gpt-4"
        assert tenant.get_config("no_existe", "default") == "default"
    
    def test_is_plan(self):
        """Test: Verificar plan del tenant"""
        tenant = TenantContext(
            tenant_id="test-202",
            tenant_name="Plan Test",
            plan="Pro"  # Mayúscula para probar case-insensitive
        )
        
        assert tenant.is_plan("pro") == True
        assert tenant.is_plan("PRO") == True
        assert tenant.is_plan("free") == False


# ============================================
# TESTS DE TENANTCONTEXTMANAGER
# ============================================

class TestTenantContextManager:
    """Tests para la clase TenantContextManager"""
    
    def setup_method(self):
        """Se ejecuta antes de cada test - Limpia el contexto"""
        TenantContextManager.clear()
    
    def teardown_method(self):
        """Se ejecuta después de cada test - Limpia el contexto"""
        TenantContextManager.clear()
    
    def test_set_and_get_current(self):
        """Test: Establecer y obtener tenant actual"""
        tenant = TenantContext(
            tenant_id="test-303",
            tenant_name="Context Test",
            plan="free"
        )
        
        # Establecer tenant
        TenantContextManager.set_current(tenant)
        
        # Obtener tenant
        current = TenantContextManager.get_current()
        
        assert current is not None
        assert current.tenant_id == "test-303"
        assert current.tenant_name == "Context Test"
    
    def test_get_current_sin_establecer(self):
        """Test: Obtener tenant cuando no hay ninguno establecido"""
        current = TenantContextManager.get_current()
        assert current is None
    
    def test_get_current_or_fail(self):
        """Test: get_current_or_fail lanza excepción si no hay tenant"""
        # Sin tenant establecido
        with pytest.raises(ValueError, match="No hay tenant establecido"):
            TenantContextManager.get_current_or_fail()
        
        # Con tenant establecido
        tenant = TenantContext(
            tenant_id="test-404",
            tenant_name="Fail Test",
            plan="pro"
        )
        TenantContextManager.set_current(tenant)
        
        current = TenantContextManager.get_current_or_fail()
        assert current.tenant_id == "test-404"
    
    def test_clear(self):
        """Test: Limpiar contexto"""
        tenant = TenantContext(
            tenant_id="test-505",
            tenant_name="Clear Test",
            plan="free"
        )
        
        # Establecer y verificar
        TenantContextManager.set_current(tenant)
        assert TenantContextManager.get_current() is not None
        
        # Limpiar y verificar
        TenantContextManager.clear()
        assert TenantContextManager.get_current() is None
    
    def test_count_active(self):
        """Test: Contar contextos activos"""
        # Sin contextos
        assert TenantContextManager.count_active() == 0
        
        # Con un contexto
        tenant = TenantContext(
            tenant_id="test-606",
            tenant_name="Count Test",
            plan="pro"
        )
        TenantContextManager.set_current(tenant)
        assert TenantContextManager.count_active() == 1
        
        # Después de limpiar
        TenantContextManager.clear()
        assert TenantContextManager.count_active() == 0
    
    def test_multiple_tenants_diferentes_threads(self):
        """Test: Múltiples tenants en diferentes threads no se mezclan"""
        import threading
        
        tenant1 = TenantContext(
            tenant_id="test-707",
            tenant_name="Thread Test 1",
            plan="free"
        )
        
        tenant2 = TenantContext(
            tenant_id="test-808",
            tenant_name="Thread Test 2",
            plan="pro"
        )
        
        # Establecer tenant1 en thread principal
        TenantContextManager.set_current(tenant1)
        
        # Variable para guardar resultado del thread secundario
        resultado = {"tenant_id": None}
        
        def thread_secundario():
            # Establecer tenant2 en thread secundario
            TenantContextManager.set_current(tenant2)
            current = TenantContextManager.get_current()
            resultado["tenant_id"] = current.tenant_id
        
        # Ejecutar thread secundario
        thread = threading.Thread(target=thread_secundario)
        thread.start()
        thread.join()
        
        # Verificar que cada thread tiene su propio tenant
        current_principal = TenantContextManager.get_current()
        assert current_principal.tenant_id == "test-707"
        assert resultado["tenant_id"] == "test-808"


# ============================================
# TESTS DEL DECORADOR
# ============================================

class TestRequireTenantDecorator:
    """Tests para el decorador @require_tenant"""
    
    def setup_method(self):
        """Limpia el contexto antes de cada test"""
        TenantContextManager.clear()
    
    def teardown_method(self):
        """Limpia el contexto después de cada test"""
        TenantContextManager.clear()
    
    def test_decorador_con_tenant(self):
        """Test: Función decorada funciona cuando hay tenant"""
        
        @require_tenant
        def funcion_que_requiere_tenant():
            tenant = TenantContextManager.get_current()
            return tenant.tenant_name
        
        # Establecer tenant
        tenant = TenantContext(
            tenant_id="test-909",
            tenant_name="Decorator Test",
            plan="free"
        )
        TenantContextManager.set_current(tenant)
        
        # Ejecutar función
        resultado = funcion_que_requiere_tenant()
        assert resultado == "Decorator Test"
    
    def test_decorador_sin_tenant(self):
        """Test: Función decorada falla cuando no hay tenant"""
        
        @require_tenant
        def funcion_que_requiere_tenant():
            return "No debería llegar aquí"
        
        # Intentar ejecutar sin tenant
        with pytest.raises(ValueError, match="requiere un tenant en el contexto"):
            funcion_que_requiere_tenant()


# ============================================
# EJECUTAR TESTS
# ============================================

if __name__ == "__main__":
    """
    Ejecutar tests directamente
    """
    pytest.main([__file__, "-v", "--tb=short"])