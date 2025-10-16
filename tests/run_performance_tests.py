#!/usr/bin/env python3
"""
Performance test runner for AFS Prometheus metrics system.

This script runs comprehensive performance tests and generates a performance report.
It can be used for continuous performance monitoring and regression testing.
"""

import sys
import time
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any
import subprocess
import psutil
import os


class PerformanceTestRunner:
    """Runner for performance tests with reporting capabilities."""
    
    def __init__(self, output_dir: str = "performance_reports"):
        """Initialize the performance test runner."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results = {}
        self.start_time = None
        self.system_info = self._get_system_info()
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information for the performance report."""
        return {
            'cpu_count': psutil.cpu_count(),
            'cpu_count_logical': psutil.cpu_count(logical=True),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
            'python_version': sys.version,
            'platform': sys.platform
        }
    
    def run_test_suite(self, test_pattern: str = None, verbose: bool = False) -> Dict[str, Any]:
        """
        Run the performance test suite.
        
        Args:
            test_pattern: Optional pattern to filter tests
            verbose: Enable verbose output
            
        Returns:
            Dictionary containing test results and performance metrics
        """
        self.start_time = time.time()
        
        # Determine which tests to run
        if test_pattern:
            test_cmd = f"tests/test_performance.py::{test_pattern}"
        else:
            test_cmd = "tests/test_performance.py"
        
        # Build pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            test_cmd,
            "-v" if verbose else "-q",
            "--tb=short",
            "--json-report",
            f"--json-report-file={self.output_dir}/pytest_report.json"
        ]
        
        print(f"Running performance tests: {' '.join(cmd)}")
        print(f"System info: {self.system_info['cpu_count']} CPUs, "
              f"{self.system_info['memory_total_gb']:.1f}GB RAM")
        print("-" * 80)
        
        # Run tests and capture output
        start_memory = psutil.virtual_memory()
        start_cpu_percent = psutil.cpu_percent(interval=1)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            end_memory = psutil.virtual_memory()
            end_cpu_percent = psutil.cpu_percent(interval=1)
            
            # Parse results
            self.results = {
                'success': result.returncode == 0,
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'duration': time.time() - self.start_time,
                'system_info': self.system_info,
                'resource_usage': {
                    'start_memory_percent': start_memory.percent,
                    'end_memory_percent': end_memory.percent,
                    'start_cpu_percent': start_cpu_percent,
                    'end_cpu_percent': end_cpu_percent,
                    'memory_available_gb': end_memory.available / (1024**3)
                }
            }
            
            # Load detailed pytest results if available
            pytest_report_file = self.output_dir / "pytest_report.json"
            if pytest_report_file.exists():
                with open(pytest_report_file) as f:
                    pytest_data = json.load(f)
                    self.results['pytest_report'] = pytest_data
            
            return self.results
            
        except subprocess.TimeoutExpired:
            self.results = {
                'success': False,
                'error': 'Tests timed out after 300 seconds',
                'duration': time.time() - self.start_time,
                'system_info': self.system_info
            }
            return self.results
    
    def generate_report(self, output_file: str = None) -> str:
        """
        Generate a performance test report.
        
        Args:
            output_file: Optional output file path
            
        Returns:
            Report content as string
        """
        if not self.results:
            return "No test results available. Run tests first."
        
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Build report
        report_lines = [
            "AFS Prometheus Metrics - Performance Test Report",
            "=" * 60,
            f"Generated: {timestamp}",
            f"Duration: {self.results.get('duration', 0):.2f} seconds",
            "",
            "System Information:",
            f"  CPU Cores: {self.system_info['cpu_count']} physical, {self.system_info['cpu_count_logical']} logical",
            f"  Memory: {self.system_info['memory_total_gb']:.1f} GB",
            f"  Platform: {self.system_info['platform']}",
            f"  Python: {self.system_info['python_version'].split()[0]}",
            ""
        ]
        
        # Test results summary
        if self.results['success']:
            report_lines.extend([
                "Test Results: PASSED ✓",
                ""
            ])
            
            # Parse pytest report for detailed results
            if 'pytest_report' in self.results:
                pytest_data = self.results['pytest_report']
                summary = pytest_data.get('summary', {})
                
                report_lines.extend([
                    "Test Summary:",
                    f"  Total: {summary.get('total', 0)}",
                    f"  Passed: {summary.get('passed', 0)}",
                    f"  Failed: {summary.get('failed', 0)}",
                    f"  Skipped: {summary.get('skipped', 0)}",
                    ""
                ])
                
                # Individual test results
                tests = pytest_data.get('tests', [])
                if tests:
                    report_lines.extend([
                        "Individual Test Results:",
                        "-" * 40
                    ])
                    
                    for test in tests:
                        name = test.get('nodeid', 'Unknown').split('::')[-1]
                        outcome = test.get('outcome', 'unknown')
                        duration = test.get('duration', 0)
                        
                        status_symbol = "✓" if outcome == "passed" else "✗"
                        report_lines.append(f"  {status_symbol} {name:<50} {duration:>8.3f}s")
                    
                    report_lines.append("")
        else:
            report_lines.extend([
                "Test Results: FAILED ✗",
                ""
            ])
            
            if 'error' in self.results:
                report_lines.extend([
                    f"Error: {self.results['error']}",
                    ""
                ])
        
        # Resource usage
        if 'resource_usage' in self.results:
            usage = self.results['resource_usage']
            report_lines.extend([
                "Resource Usage:",
                f"  Memory Usage: {usage['start_memory_percent']:.1f}% → {usage['end_memory_percent']:.1f}%",
                f"  CPU Usage: {usage['start_cpu_percent']:.1f}% → {usage['end_cpu_percent']:.1f}%",
                f"  Available Memory: {usage['memory_available_gb']:.1f} GB",
                ""
            ])
        
        # Performance recommendations
        report_lines.extend([
            "Performance Analysis:",
            "-" * 30
        ])
        
        if self.results['success'] and 'pytest_report' in self.results:
            tests = self.results['pytest_report'].get('tests', [])
            slow_tests = [t for t in tests if t.get('duration', 0) > 5.0]
            
            if slow_tests:
                report_lines.extend([
                    "⚠️  Slow Tests (>5s):"
                ])
                for test in slow_tests:
                    name = test.get('nodeid', 'Unknown').split('::')[-1]
                    duration = test.get('duration', 0)
                    report_lines.append(f"    {name}: {duration:.2f}s")
                report_lines.append("")
            
            # Memory usage analysis
            if 'resource_usage' in self.results:
                usage = self.results['resource_usage']
                memory_increase = usage['end_memory_percent'] - usage['start_memory_percent']
                
                if memory_increase > 10:
                    report_lines.extend([
                        f"⚠️  High memory usage increase: {memory_increase:.1f}%",
                        "    Consider investigating memory leaks or optimizing data structures.",
                        ""
                    ])
                elif memory_increase < 2:
                    report_lines.extend([
                        "✓ Good memory usage - minimal increase during tests",
                        ""
                    ])
        
        # Add stdout/stderr if there were issues
        if not self.results['success']:
            if self.results.get('stderr'):
                report_lines.extend([
                    "Error Output:",
                    "-" * 20,
                    self.results['stderr'],
                    ""
                ])
        
        report_content = "\n".join(report_lines)
        
        # Save to file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(report_content)
            print(f"Report saved to: {output_path}")
        
        return report_content
    
    def run_benchmark_suite(self) -> Dict[str, Any]:
        """
        Run a focused benchmark suite for key performance metrics.
        
        Returns:
            Dictionary with benchmark results
        """
        benchmarks = {
            'concurrent_light': 'TestConcurrentRequests::test_concurrent_metrics_requests_light_load',
            'concurrent_heavy': 'TestConcurrentRequests::test_concurrent_metrics_requests_heavy_load',
            'memory_large': 'TestMemoryUsage::test_memory_usage_large_response',
            'large_directories': 'TestLargeDirectoryHandling::test_processing_many_directories'
        }
        
        benchmark_results = {}
        
        for benchmark_name, test_pattern in benchmarks.items():
            print(f"\nRunning benchmark: {benchmark_name}")
            print("-" * 40)
            
            result = self.run_test_suite(test_pattern, verbose=False)
            benchmark_results[benchmark_name] = {
                'success': result['success'],
                'duration': result['duration'],
                'resource_usage': result.get('resource_usage', {})
            }
            
            if result['success']:
                print(f"✓ {benchmark_name}: {result['duration']:.2f}s")
            else:
                print(f"✗ {benchmark_name}: FAILED")
        
        return benchmark_results


def main():
    """Main entry point for the performance test runner."""
    parser = argparse.ArgumentParser(description="Run AFS Prometheus metrics performance tests")
    parser.add_argument('--test', '-t', help="Specific test pattern to run")
    parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
    parser.add_argument('--output', '-o', help="Output file for report")
    parser.add_argument('--benchmark', '-b', action='store_true', help="Run benchmark suite")
    parser.add_argument('--output-dir', default="performance_reports", help="Output directory for reports")
    
    args = parser.parse_args()
    
    # Create runner
    runner = PerformanceTestRunner(output_dir=args.output_dir)
    
    try:
        if args.benchmark:
            print("Running benchmark suite...")
            benchmark_results = runner.run_benchmark_suite()
            
            # Generate benchmark report
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            benchmark_file = f"benchmark_report_{timestamp}.txt"
            
            report_lines = [
                "AFS Prometheus Metrics - Benchmark Report",
                "=" * 50,
                f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                ""
            ]
            
            for benchmark_name, result in benchmark_results.items():
                status = "PASSED" if result['success'] else "FAILED"
                duration = result['duration']
                report_lines.append(f"{benchmark_name:<20} {status:<8} {duration:>8.2f}s")
            
            benchmark_report = "\n".join(report_lines)
            
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(benchmark_report)
                print(f"\nBenchmark report saved to: {args.output}")
            else:
                print("\n" + benchmark_report)
        
        else:
            # Run full test suite
            print("Running performance test suite...")
            results = runner.run_test_suite(args.test, args.verbose)
            
            # Generate report
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            default_output = args.output or f"performance_report_{timestamp}.txt"
            
            report = runner.generate_report(default_output)
            
            if not args.output:
                print("\n" + report)
            
            # Exit with appropriate code
            sys.exit(0 if results['success'] else 1)
    
    except KeyboardInterrupt:
        print("\nTest run interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error running performance tests: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()