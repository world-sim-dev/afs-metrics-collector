# Performance Testing Guide

This document describes the performance testing framework for the AFS Prometheus metrics system.

## Overview

The performance testing suite validates that the system can handle:
- Concurrent scrape requests from multiple Prometheus instances
- Large numbers of directories (10,000+)
- Long-running operations without memory leaks
- High-throughput scenarios

## Test Categories

### 1. Concurrent Request Tests (`TestConcurrentRequests`)

Tests server performance under concurrent load:

- **Light Load**: 10 concurrent requests
- **Heavy Load**: 50 concurrent requests with 20 max workers
- **Sustained Load**: Multiple batches over time to test stability

**Performance Criteria:**
- Average response time < 2s (light), < 5s (heavy)
- 95th percentile response time < 10s (heavy load)
- Memory increase < 50MB (light), < 100MB (heavy)
- Throughput > 2 req/s (light), > 1 req/s (heavy)

### 2. Memory Usage Tests (`TestMemoryUsage`)

Validates memory efficiency and leak detection:

- **Large Response Processing**: 5,000 directories per request
- **Multiple Volume Processing**: 20 volumes with varied directory counts
- **Sustained Processing**: Multiple iterations to detect leaks

**Performance Criteria:**
- Total memory increase < 200-500MB depending on data size
- No continuous memory growth (leak detection)
- Performance degradation < 2x over time

### 3. Large Directory Handling (`TestLargeDirectoryHandling`)

Tests behavior with large datasets:

- **Many Directories**: 10,000 directories in single response
- **Label Sanitization**: Performance with special characters
- **Mixed Sizes**: Combination of small and large directories

**Performance Criteria:**
- Processing time < 30s for 10,000 directories
- Memory increase < 500MB for large datasets
- Label sanitization < 5s for 1,000 directories

## Running Performance Tests

### Basic Usage

```bash
# Run all performance tests
python -m pytest tests/test_performance.py -v

# Run specific test category
python -m pytest tests/test_performance.py::TestConcurrentRequests -v

# Run single test
python -m pytest tests/test_performance.py::TestConcurrentRequests::test_concurrent_metrics_requests_light_load -v
```

### Using the Performance Runner

The performance runner provides enhanced reporting and benchmarking:

```bash
# Run full performance suite with report
python tests/run_performance_tests.py

# Run benchmark suite (key tests only)
python tests/run_performance_tests.py --benchmark

# Run specific test with verbose output
python tests/run_performance_tests.py --test TestConcurrentRequests --verbose

# Save report to specific file
python tests/run_performance_tests.py --output performance_report.txt
```

### Command Line Options

- `--test, -t`: Run specific test pattern
- `--verbose, -v`: Enable verbose output
- `--output, -o`: Specify output file for report
- `--benchmark, -b`: Run benchmark suite only
- `--output-dir`: Directory for reports (default: performance_reports)

## Performance Benchmarks

### Expected Performance Characteristics

Based on system specifications:

| Test Scenario | Expected Duration | Memory Usage | Throughput |
|---------------|------------------|--------------|------------|
| Light Concurrent (10 req) | < 2s | < 50MB | > 2 req/s |
| Heavy Concurrent (50 req) | < 10s | < 100MB | > 1 req/s |
| Large Response (5K dirs) | < 5s | < 200MB | N/A |
| Very Large (10K dirs) | < 30s | < 500MB | N/A |

### System Requirements

Minimum recommended specifications:
- CPU: 2+ cores
- Memory: 4GB+ available
- Python: 3.8+

Optimal specifications:
- CPU: 4+ cores
- Memory: 8GB+ available
- SSD storage for faster I/O

## Interpreting Results

### Response Time Analysis

- **Average Response Time**: Should remain consistent under load
- **95th Percentile**: Indicates worst-case user experience
- **Maximum Response Time**: Should not exceed timeout limits

### Memory Usage Analysis

- **Memory Increase**: Should be proportional to data size
- **Memory Stability**: No continuous growth indicates no leaks
- **Peak Memory**: Should not exceed available system memory

### Throughput Analysis

- **Requests per Second**: Indicates server capacity
- **Concurrent Handling**: Tests thread safety and resource sharing
- **Cache Effectiveness**: Reduced API calls indicate good caching

## Performance Optimization Tips

### Server Configuration

```yaml
# Optimal configuration for performance
server:
  host: "0.0.0.0"
  port: 8080
  request_timeout: 30

collection:
  max_retries: 3
  retry_delay: 1
  timeout_seconds: 25
  cache_duration: 30  # Balance freshness vs performance
```

### System Tuning

1. **Memory**: Ensure adequate RAM for dataset size
2. **CPU**: Multi-core systems handle concurrent requests better
3. **Network**: Low latency to AFS API improves response times
4. **Caching**: Tune cache duration based on scrape frequency

### Monitoring in Production

Key metrics to monitor:
- Response time percentiles (50th, 95th, 99th)
- Memory usage trends
- CPU utilization during scrapes
- Cache hit rates
- Error rates under load

## Troubleshooting Performance Issues

### High Response Times

1. Check AFS API latency
2. Verify network connectivity
3. Review cache configuration
4. Monitor CPU/memory usage

### Memory Issues

1. Check for memory leaks in logs
2. Verify garbage collection is working
3. Review dataset sizes
4. Monitor memory growth over time

### Concurrent Request Problems

1. Verify thread safety
2. Check for resource contention
3. Review cache synchronization
4. Monitor database connections

## Continuous Performance Testing

### CI/CD Integration

Add performance tests to your CI pipeline:

```yaml
# Example GitHub Actions workflow
- name: Run Performance Tests
  run: |
    python tests/run_performance_tests.py --benchmark
    if [ $? -ne 0 ]; then
      echo "Performance tests failed"
      exit 1
    fi
```

### Performance Regression Detection

Set up automated alerts for:
- Response time increases > 50%
- Memory usage increases > 100MB
- Throughput decreases > 25%
- Test failures

### Regular Benchmarking

Schedule regular performance runs:
- Daily: Quick benchmark suite
- Weekly: Full performance test suite
- Monthly: Comprehensive analysis with trending

## Performance Test Data

### Test Data Generation

The performance tests use `PerformanceTestHelper.create_large_afs_response()` to generate realistic test data:

- Configurable number of directories
- Realistic file counts and sizes
- Mix of directories with/without quotas
- Varied volume IDs and zones

### Customizing Test Data

To test with your specific data patterns:

```python
# Create custom test response
custom_response = {
    "dir_quota_list": [
        {
            "volume_id": "your-volume-id",
            "dir_path": "/your/path",
            "file_quantity_quota": 1000000,
            "file_quantity_used_quota": 500000,
            "capacity_quota": 1073741824000,  # 1TB
            "capacity_used_quota": 536870912000,  # 500GB
            "state": 1
        }
        # Add more directories as needed
    ]
}
```

## Dependencies

Performance testing requires additional dependencies:

```
psutil==5.9.5              # System resource monitoring
pytest-json-report==1.5.0  # Enhanced test reporting
```

These are automatically included in `requirements.txt`.

## Best Practices

1. **Consistent Environment**: Run tests in consistent environments
2. **Baseline Measurements**: Establish performance baselines
3. **Regular Monitoring**: Track performance trends over time
4. **Resource Isolation**: Avoid running other intensive processes during tests
5. **Multiple Runs**: Average results across multiple test runs
6. **Documentation**: Document any performance optimizations made

## Reporting Issues

When reporting performance issues, include:
- System specifications (CPU, memory, OS)
- Test results and logs
- Performance report output
- Comparison with expected benchmarks
- Steps to reproduce the issue