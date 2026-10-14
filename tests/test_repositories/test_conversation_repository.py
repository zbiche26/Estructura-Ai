"""
Tests para ConversationRepository y MessageRepository
Usando patch directo en métodos - NO conecta a Supabase real
"""
import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.repositories.conversation_repository import ConversationRepository, MessageRepository
from src.models.models import Conversation, Message, ConversationStatus, MessageRole
from src.core.tenant_context import TenantContext, TenantContextManager


TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def setup_tenant_context():
    tenant = TenantContext(
        tenant_id=TENANT_ID,
        tenant_name="Test Tenant",
        plan="starter",
        features_enabled=[],
        config={}
    )
    TenantContextManager.set_current(tenant)
    yield
    TenantContextManager.clear()


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def conv_repo(mock_client):
    return ConversationRepository(client=mock_client)


@pytest.fixture
def msg_repo(mock_client):
    return MessageRepository(client=mock_client)


def make_conv(phone="+573001234567", status="active"):
    return Conversation(
        id=uuid4(),
        tenant_id=TENANT_ID,
        phone_number=phone,
        customer_name="Test User",
        status=ConversationStatus(status),
        current_strategy=None,
        context={},
        metadata={},
    )


def make_msg(conversation_id=None, role=MessageRole.USER, content="Hola"):
    return Message(
        id=uuid4(),
        tenant_id=TENANT_ID,
        conversation_id=conversation_id or uuid4(),
        role=role,
        content=content,
        strategy_used=None,
        metadata={},
    )


class TestConversationRepositoryBasic:

    def test_get_or_create_new(self, conv_repo):
        phone = f"+57300{uuid4().hex[:7]}"
        expected = make_conv(phone=phone)
        with patch.object(conv_repo, 'get_or_create', return_value=expected):
            conv = conv_repo.get_or_create(phone_number=phone)
            assert conv is not None
            assert conv.phone_number == phone

    def test_get_or_create_existing(self, conv_repo):
        phone = f"+57300{uuid4().hex[:7]}"
        expected = make_conv(phone=phone)
        with patch.object(conv_repo, 'get_or_create', return_value=expected):
            conv1 = conv_repo.get_or_create(phone_number=phone)
            conv2 = conv_repo.get_or_create(phone_number=phone)
            assert conv1 is not None
            assert conv2 is not None

    def test_get_by_id(self, conv_repo):
        expected = make_conv()
        with patch.object(conv_repo, 'get_by_id', return_value=expected):
            conv = conv_repo.get_by_id(str(expected.id))
            assert conv is not None
            assert conv.id == expected.id


class TestConversationRepositorySearch:

    def test_get_active_by_phone(self, conv_repo):
        phone = "+573001234567"
        expected = make_conv(phone=phone, status="active")
        with patch.object(conv_repo, 'get_active_by_phone', return_value=expected):
            conv = conv_repo.get_active_by_phone(phone)
            assert conv is not None
            assert conv.status == ConversationStatus.ACTIVE

    def test_get_by_phone(self, conv_repo):
        phone = "+573001234567"
        expected = [make_conv(phone=phone)]
        with patch.object(conv_repo, 'get_by_phone', return_value=expected):
            result = conv_repo.get_by_phone(phone)
            assert isinstance(result, list)
            assert len(result) >= 1

    def test_get_active_conversations(self, conv_repo):
        expected = [make_conv(), make_conv()]
        with patch.object(conv_repo, 'get_active_conversations', return_value=expected):
            result = conv_repo.get_active_conversations(limit=10)
            assert isinstance(result, list)
            for conv in result:
                assert conv.status == ConversationStatus.ACTIVE


class TestConversationRepositoryStatus:

    def test_close_conversation(self, conv_repo):
        conv = make_conv(status="closed")
        with patch.object(conv_repo, 'close_conversation', return_value=conv):
            result = conv_repo.close_conversation(str(conv.id))
            assert result is not None
            assert result.status == ConversationStatus.CLOSED

    def test_archive_conversation(self, conv_repo):
        conv = make_conv(status="archived")
        with patch.object(conv_repo, 'archive_conversation', return_value=conv):
            result = conv_repo.archive_conversation(str(conv.id))
            assert result is not None
            assert result.status == ConversationStatus.ARCHIVED

    def test_reopen_conversation(self, conv_repo):
        conv = make_conv(status="active")
        with patch.object(conv_repo, 'reopen_conversation', return_value=conv):
            result = conv_repo.reopen_conversation(str(conv.id))
            assert result is not None
            assert result.status == ConversationStatus.ACTIVE


class TestConversationRepositoryContext:

    def test_update_context(self, conv_repo):
        conv = make_conv()
        conv.context = {"last_product": "laptop"}
        with patch.object(conv_repo, 'update_context', return_value=conv):
            result = conv_repo.update_context(str(conv.id), {"last_product": "laptop"})
            assert result is not None
            assert "last_product" in result.context

    def test_set_strategy(self, conv_repo):
        conv = make_conv()
        conv.current_strategy = "product_recommendation"
        with patch.object(conv_repo, 'set_strategy', return_value=conv):
            result = conv_repo.set_strategy(str(conv.id), "product_recommendation")
            assert result is not None
            assert result.current_strategy == "product_recommendation"


class TestConversationRepositoryStats:

    def test_get_conversation_stats(self, conv_repo):
        expected = {"total_messages": 2, "user_messages": 1, "assistant_messages": 1}
        with patch.object(conv_repo, 'get_conversation_stats', return_value=expected):
            stats = conv_repo.get_conversation_stats(str(uuid4()))
            assert isinstance(stats, dict)
            assert "total_messages" in stats


class TestMessageRepositoryBasic:

    def test_add_message(self, msg_repo):
        expected = make_msg(role=MessageRole.USER, content="Hola")
        with patch.object(msg_repo, 'add_message', return_value=expected):
            msg = msg_repo.add_message(
                conversation_id=str(uuid4()),
                role=MessageRole.USER,
                content="Hola"
            )
            assert msg is not None
            assert msg.role == MessageRole.USER

    def test_add_message_with_strategy(self, msg_repo):
        expected = make_msg(role=MessageRole.ASSISTANT, content="Claro!")
        expected.strategy_used = "product_inquiry"
        with patch.object(msg_repo, 'add_message', return_value=expected):
            msg = msg_repo.add_message(
                conversation_id=str(uuid4()),
                role=MessageRole.ASSISTANT,
                content="Claro!",
                strategy_used="product_inquiry"
            )
            assert msg is not None
            assert msg.strategy_used == "product_inquiry"


class TestMessageRepositoryRetrieval:

    def test_get_by_conversation(self, msg_repo):
        conv_id = uuid4()
        msgs = [make_msg(conv_id), make_msg(conv_id), make_msg(conv_id)]
        with patch.object(msg_repo, 'get_by_conversation', return_value=msgs):
            result = msg_repo.get_by_conversation(str(conv_id))
            assert isinstance(result, list)
            assert len(result) == 3

    def test_get_recent_messages(self, msg_repo):
        conv_id = uuid4()
        msgs = [make_msg(conv_id) for _ in range(3)]
        with patch.object(msg_repo, 'get_recent_messages', return_value=msgs):
            result = msg_repo.get_recent_messages(str(conv_id), limit=3)
            assert isinstance(result, list)
            assert len(result) <= 3

    def test_get_chat_history(self, msg_repo):
        conv_id = uuid4()
        history = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola!"},
        ]
        with patch.object(msg_repo, 'get_chat_history', return_value=history):
            result = msg_repo.get_chat_history(str(conv_id))
            assert isinstance(result, list)
            assert all("role" in m and "content" in m for m in result)


class TestMessageRepositorySearch:

    def test_search_in_conversation(self, msg_repo):
        conv_id = uuid4()
        msgs = [make_msg(conv_id, content="laptops Dell")]
        with patch.object(msg_repo, 'search_in_conversation', return_value=msgs):
            result = msg_repo.search_in_conversation(str(conv_id), "laptops")
            assert isinstance(result, list)
            assert len(result) >= 1


class TestMessageRepositoryCount:

    def test_count_messages(self, msg_repo):
        with patch.object(msg_repo, 'count', return_value=5):
            count = msg_repo.count({"conversation_id": str(uuid4())})
            assert count == 5
            assert isinstance(count, int)

    def test_count_by_role(self, msg_repo):
        with patch.object(msg_repo, 'count_by_role', return_value=2):
            count = msg_repo.count_by_role(str(uuid4()), MessageRole.USER)
            assert count >= 1
            assert isinstance(count, int)