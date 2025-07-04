#!/usr/bin/env python3
"""
Workflows Package

This package contains specialized workflow modules for different coding use cases,
each using the unified Orchestrator with specific functionality and prompts tailored for particular tasks.
"""

from .bug_hunting import BugHunter
from .custom_coding import CustomCodingWorkflow
from .code_optimization import CodeOptimizer
from .test_workflow import TestWorkflow

__all__ = [
    'BugHunter',
    'CustomCodingWorkflow', 
    'CodeOptimizer',
    'TestWorkflow'
] 