"""
Shared pytest fixtures and configuration for all tests.
"""
import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta
from typing import Generator, Dict, Any, List

import pytest

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ==================== Directory and File Fixtures ====================

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def temp_file(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a temporary file for testing."""
    temp_file_path = temp_dir / "test_file.txt"
    temp_file_path.write_text("test content")
    yield temp_file_path


@pytest.fixture
def sample_html_file(temp_dir: Path) -> Path:
    """Create a sample HTML file for testing."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>Test Header</h1>
        <p>Test paragraph content.</p>
        <a href="http://example.onion">Onion Link</a>
    </body>
    </html>
    """
    html_file = temp_dir / "test.html"
    html_file.write_text(html_content)
    return html_file


# ==================== Configuration Fixtures ====================

@pytest.fixture
def test_config() -> Dict[str, Any]:
    """Provide test configuration settings."""
    return {
        "database": {
            "host": "localhost",
            "port": 3306,
            "user": "test_user",
            "password": "test_pass",
            "database": "test_db"
        },
        "elasticsearch": {
            "host": "localhost",
            "port": 9200,
            "index": "test_index"
        },
        "tor": {
            "proxy_host": "127.0.0.1",
            "proxy_port": 9050,
            "control_port": 9051
        },
        "scraper": {
            "timeout": 30,
            "max_retries": 3,
            "user_agent": "Test Bot 1.0"
        },
        "paths": {
            "data_dir": "/tmp/test_data",
            "log_dir": "/tmp/test_logs",
            "cache_dir": "/tmp/test_cache"
        }
    }


@pytest.fixture
def env_vars(monkeypatch) -> None:
    """Set up test environment variables."""
    test_env = {
        "DATABASE_URL": "mysql://test_user:test_pass@localhost:3306/test_db",
        "ELASTICSEARCH_URL": "http://localhost:9200",
        "TOR_PROXY": "socks5://127.0.0.1:9050",
        "DEBUG": "True",
        "TESTING": "True"
    }
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)


# ==================== Mock Objects Fixtures ====================

@pytest.fixture
def mock_database() -> Mock:
    """Create a mock database connection."""
    mock_db = Mock()
    mock_db.execute.return_value = Mock()
    mock_db.fetchall.return_value = []
    mock_db.fetchone.return_value = None
    mock_db.commit.return_value = None
    mock_db.rollback.return_value = None
    return mock_db


@pytest.fixture
def mock_elasticsearch() -> Mock:
    """Create a mock Elasticsearch client."""
    mock_es = Mock()
    mock_es.index.return_value = {"_id": "test_id", "result": "created"}
    mock_es.search.return_value = {
        "hits": {
            "total": {"value": 0},
            "hits": []
        }
    }
    mock_es.ping.return_value = True
    return mock_es


@pytest.fixture
def mock_tor_session() -> Mock:
    """Create a mock Tor session."""
    mock_session = Mock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>Test content</body></html>"
    mock_response.content = b"<html><body>Test content</body></html>"
    mock_response.headers = {"Content-Type": "text/html"}
    mock_session.get.return_value = mock_response
    mock_session.post.return_value = mock_response
    return mock_session


# ==================== Data Fixtures ====================

@pytest.fixture
def sample_onion_data() -> Dict[str, Any]:
    """Provide sample onion site data."""
    return {
        "domain": "test123onion.onion",
        "url": "http://test123onion.onion",
        "title": "Test Onion Site",
        "description": "A test onion site for unit testing",
        "last_seen": datetime.now().isoformat(),
        "first_seen": (datetime.now() - timedelta(days=30)).isoformat(),
        "status": "online",
        "language": "en",
        "category": "test",
        "ports": [80, 443],
        "services": ["http", "https"],
        "ssh_fingerprint": None,
        "bitcoin_addresses": [],
        "email_addresses": [],
        "phone_numbers": [],
        "social_media": [],
        "metadata": {
            "server": "nginx",
            "powered_by": "unknown",
            "generator": None
        }
    }


@pytest.fixture
def sample_bitcoin_addresses() -> List[str]:
    """Provide sample Bitcoin addresses for testing."""
    return [
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # Genesis block address
        "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",  # P2SH address
        "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",  # Bech32 address
    ]


@pytest.fixture
def sample_email_addresses() -> List[str]:
    """Provide sample email addresses for testing."""
    return [
        "test@example.com",
        "admin@test.onion",
        "user123@protonmail.com",
        "contact@securemail.onion"
    ]


@pytest.fixture
def sample_banned_words() -> List[str]:
    """Provide sample banned words for testing."""
    return [
        "illegal",
        "banned",
        "prohibited",
        "restricted"
    ]


# ==================== Network Fixtures ====================

@pytest.fixture
def mock_port_scanner() -> Mock:
    """Create a mock port scanner."""
    mock_scanner = Mock()
    mock_scanner.scan.return_value = {
        "scan": {
            "127.0.0.1": {
                "tcp": {
                    80: {"state": "open", "name": "http"},
                    443: {"state": "open", "name": "https"},
                    22: {"state": "closed", "name": "ssh"}
                }
            }
        }
    }
    return mock_scanner


@pytest.fixture
def mock_whatweb_output() -> Dict[str, Any]:
    """Provide mock WhatWeb output."""
    return {
        "target": "http://test.onion",
        "plugins": {
            "HTTPServer": {"string": ["nginx/1.18.0"]},
            "Country": {"string": ["RESERVED"]},
            "IP": {"string": ["127.0.0.1"]},
            "Title": {"string": ["Test Page"]},
            "X-Powered-By": {"string": ["PHP/7.4.3"]},
            "WordPress": {"version": ["5.8.1"]}
        }
    }


# ==================== Time and Date Fixtures ====================

@pytest.fixture
def frozen_time(monkeypatch) -> datetime:
    """Freeze time for consistent testing."""
    frozen = datetime(2024, 1, 1, 12, 0, 0)
    
    class MockDatetime:
        @classmethod
        def now(cls):
            return frozen
        
        @classmethod
        def utcnow(cls):
            return frozen
    
    monkeypatch.setattr("datetime.datetime", MockDatetime)
    return frozen


# ==================== Cleanup Fixtures ====================

@pytest.fixture(autouse=True)
def cleanup_test_files(request):
    """Automatically clean up test files after each test."""
    # Setup
    test_files = []
    
    def register_cleanup(filepath):
        test_files.append(filepath)
    
    request.addfinalizer(lambda: [
        os.unlink(f) for f in test_files if os.path.exists(f)
    ])
    
    return register_cleanup


# ==================== Parametrized Test Helpers ====================

def pytest_generate_tests(metafunc):
    """
    Custom test generation for parametrized tests.
    
    This allows tests to use custom markers for parametrization.
    """
    if "onion_url" in metafunc.fixturenames:
        metafunc.parametrize("onion_url", [
            "http://test.onion",
            "https://secure.onion",
            "http://3g2upl4pq3kufc4m.onion",  # DuckDuckGo onion
        ])
    
    if "http_status" in metafunc.fixturenames:
        metafunc.parametrize("http_status", [200, 404, 500, 503])


# ==================== Assertion Helpers ====================

class AssertionHelpers:
    """Helper methods for common test assertions."""
    
    @staticmethod
    def assert_valid_onion_url(url: str) -> None:
        """Assert that a URL is a valid onion address."""
        assert url.endswith(".onion") or ".onion/" in url
        assert url.startswith(("http://", "https://"))
    
    @staticmethod
    def assert_valid_bitcoin_address(address: str) -> None:
        """Assert that a string is a valid Bitcoin address format."""
        assert len(address) in [26, 34, 42, 62]  # Various Bitcoin address lengths
        assert address[0] in ["1", "3", "b"]  # Valid first characters
    
    @staticmethod
    def assert_valid_email(email: str) -> None:
        """Assert that a string is a valid email format."""
        assert "@" in email
        assert "." in email.split("@")[1]


@pytest.fixture
def assert_helpers() -> AssertionHelpers:
    """Provide assertion helper methods."""
    return AssertionHelpers()


# ==================== Performance Testing ====================

@pytest.fixture
def benchmark_timer():
    """Simple benchmark timer for performance tests."""
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None
    
    return Timer()


# ==================== Database Fixtures ====================

@pytest.fixture
def sample_database_schema() -> str:
    """Provide sample database schema for testing."""
    return """
    CREATE TABLE IF NOT EXISTS domains (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain VARCHAR(255) UNIQUE NOT NULL,
        title TEXT,
        status VARCHAR(50),
        first_seen DATETIME,
        last_seen DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain_id INTEGER,
        url TEXT NOT NULL,
        content TEXT,
        scraped_at DATETIME,
        FOREIGN KEY (domain_id) REFERENCES domains(id)
    );
    """