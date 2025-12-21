"""
Press Utils Package

Utilities for Frappe Press including shared bench multi-tenancy support.
"""

from press.press.utils.shared_bench import (
    is_shared_bench_mode,
    get_shared_bench_config,
    get_database_name,
    get_database_user,
    validate_shared_bench_config,
    SharedBenchSiteManager,
    get_shared_bench_site_manager,
)

from press.press.utils.shared_bench_agent import (
    SharedBenchAgent,
    SharedBenchJob,
    get_agent,
)

__all__ = [
    # Shared bench config
    'is_shared_bench_mode',
    'get_shared_bench_config', 
    'get_database_name',
    'get_database_user',
    'validate_shared_bench_config',
    'SharedBenchSiteManager',
    'get_shared_bench_site_manager',
    # Agent
    'SharedBenchAgent',
    'SharedBenchJob',
    'get_agent',
]


def initialize_shared_bench():
    """
    Initialize shared bench mode if enabled.
    
    This function should be called during app initialization
    (e.g., from hooks.py after_install or on_startup).
    """
    if not is_shared_bench_mode():
        return
    
    import frappe
    
    # Validate configuration
    validate_shared_bench_config()
    
    # Create virtual resources
    from press.press.utils.virtual_server import (
        ensure_virtual_server,
        ensure_virtual_bench,
    )
    
    try:
        ensure_virtual_server()
        ensure_virtual_bench()
    except Exception as e:
        frappe.log_error(f"Failed to initialize shared bench: {e}")
    
    # Install hooks
    from press.press.utils.site_patches import install_hooks
    try:
        install_hooks()
    except Exception as e:
        frappe.log_error(f"Failed to install shared bench hooks: {e}")
    
    frappe.logger().info("Shared bench mode initialized")
