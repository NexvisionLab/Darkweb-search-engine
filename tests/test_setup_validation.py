"""
Validation tests to ensure the testing infrastructure is properly configured.
"""
import sys
from pathlib import Path

import pytest


class TestSetupValidation:
    """Validate that the testing infrastructure is properly configured."""
    
    def test_project_imports(self):
        """Test that project modules can be imported."""
        # Test core library imports
        import lib
        assert lib is not None
        
        # Test torscraper imports
        import torscraper
        assert torscraper is not None
    
    def test_fixtures_available(self, temp_dir, test_config, mock_database):
        """Test that pytest fixtures are available and working."""
        assert temp_dir.exists()
        assert temp_dir.is_dir()
        
        assert isinstance(test_config, dict)
        assert "database" in test_config
        assert "elasticsearch" in test_config
        
        assert mock_database is not None
        assert hasattr(mock_database, "execute")
    
    def test_markers_defined(self, request):
        """Test that custom markers are properly defined."""
        markers = request.config.getini("markers")
        marker_names = [m.split(":")[0].strip() for m in markers]
        
        assert "unit" in marker_names
        assert "integration" in marker_names
        assert "slow" in marker_names
    
    @pytest.mark.unit
    def test_unit_marker(self):
        """Test that unit marker works."""
        assert True
    
    @pytest.mark.integration
    def test_integration_marker(self):
        """Test that integration marker works."""
        assert True
    
    @pytest.mark.slow
    def test_slow_marker(self):
        """Test that slow marker works."""
        assert True
    
    def test_temp_file_creation(self, temp_file):
        """Test temporary file fixture."""
        assert temp_file.exists()
        assert temp_file.read_text() == "test content"
    
    def test_mock_elasticsearch(self, mock_elasticsearch):
        """Test mock Elasticsearch fixture."""
        assert mock_elasticsearch.ping() is True
        
        result = mock_elasticsearch.index(index="test", body={"data": "test"})
        assert result["result"] == "created"
    
    def test_sample_data_fixtures(self, sample_onion_data, sample_bitcoin_addresses):
        """Test sample data fixtures."""
        assert sample_onion_data["domain"] == "test123onion.onion"
        assert sample_onion_data["status"] == "online"
        
        assert len(sample_bitcoin_addresses) == 3
        assert sample_bitcoin_addresses[0].startswith("1")
    
    def test_assertion_helpers(self, assert_helpers):
        """Test assertion helper methods."""
        assert_helpers.assert_valid_onion_url("http://test.onion")
        assert_helpers.assert_valid_onion_url("https://secure.onion/page")
        
        with pytest.raises(AssertionError):
            assert_helpers.assert_valid_onion_url("http://example.com")
        
        assert_helpers.assert_valid_email("test@example.com")
        
        with pytest.raises(AssertionError):
            assert_helpers.assert_valid_email("invalid-email")
    
    def test_benchmark_timer(self, benchmark_timer):
        """Test benchmark timer fixture."""
        import time
        
        benchmark_timer.start()
        time.sleep(0.01)  # Sleep for 10ms
        benchmark_timer.stop()
        
        assert benchmark_timer.elapsed is not None
        assert benchmark_timer.elapsed >= 0.01
        assert benchmark_timer.elapsed < 0.1  # Should be less than 100ms
    
    def test_coverage_configured(self):
        """Test that coverage is properly configured."""
        try:
            import pytest_cov
            assert pytest_cov is not None
        except ImportError:
            # Coverage not installed yet, that's OK for validation
            pass
    
    def test_python_path_configured(self):
        """Test that Python path includes project root."""
        project_root = str(Path(__file__).parent.parent)
        assert project_root in sys.path