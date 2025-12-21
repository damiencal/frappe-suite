"""
Virtual Server for Shared Bench Mode

In shared bench mode, all sites run on a single Kubernetes deployment.
This module provides a "virtual server" that represents this shared infrastructure
for compatibility with Press's server-centric architecture.
"""

import frappe
from press.press.utils.shared_bench import is_shared_bench_mode, get_shared_bench_config


VIRTUAL_SERVER_NAME = "shared-bench-server"
VIRTUAL_SERVER_TITLE = "Shared Kubernetes Bench"


def ensure_virtual_server():
    """
    Ensure the virtual server document exists.
    
    Creates it if it doesn't exist with proper configuration.
    
    Returns:
        str: Name of the virtual server
    """
    if not is_shared_bench_mode():
        frappe.throw("Virtual server is only used in shared bench mode")
    
    config = get_shared_bench_config()
    server_name = config.get('virtual_server_name', VIRTUAL_SERVER_NAME)
    
    if frappe.db.exists("Server", server_name):
        return server_name
    
    # Create the virtual server
    server = frappe.get_doc({
        "doctype": "Server",
        "name": server_name,
        "title": VIRTUAL_SERVER_TITLE,
        "status": "Active",
        "is_virtual": 1,  # Custom field to mark as virtual
        "hostname": server_name,
        "ip": "127.0.0.1",  # Placeholder IP
        "agent_password": frappe.generate_hash(length=32),
        # Mark as self-managed (no provisioning)
        "is_self_managed": 1,
        # Disable health checks (shared bench manages itself)
        "skip_scheduled_backups": 1,
    })
    
    # Insert with custom name
    server.flags.ignore_links = True
    server.flags.ignore_mandatory = True
    server.db_insert()
    
    frappe.db.commit()
    frappe.logger().info(f"Created virtual server: {server_name}")
    
    return server_name


def get_virtual_server():
    """
    Get the virtual server document.
    
    Creates it if it doesn't exist.
    
    Returns:
        Server document
    """
    server_name = ensure_virtual_server()
    return frappe.get_doc("Server", server_name)


def ensure_virtual_bench(bench_name=None):
    """
    Ensure the virtual bench document exists.
    
    In shared bench mode, there's one "virtual" bench representing
    the shared ERPNext installation.
    
    Args:
        bench_name: Optional name for the bench
    
    Returns:
        str: Name of the virtual bench
    """
    if not is_shared_bench_mode():
        frappe.throw("Virtual bench is only used in shared bench mode")
    
    config = get_shared_bench_config()
    bench_name = bench_name or config.get('virtual_bench_name', 'shared-bench')
    
    if frappe.db.exists("Bench", bench_name):
        return bench_name
    
    # Get the virtual server
    server_name = ensure_virtual_server()
    
    # Get or create a release group for the shared bench
    release_group = ensure_virtual_release_group()
    
    # Create the virtual bench
    bench = frappe.get_doc({
        "doctype": "Bench",
        "name": bench_name,
        "server": server_name,
        "status": "Active",
        "is_virtual": 1,
        "group": release_group,
    })
    
    bench.flags.ignore_links = True
    bench.flags.ignore_mandatory = True
    bench.db_insert()
    
    frappe.db.commit()
    frappe.logger().info(f"Created virtual bench: {bench_name}")
    
    return bench_name


def ensure_virtual_release_group():
    """
    Ensure a release group exists for the shared bench.
    
    Returns:
        str: Name of the release group
    """
    config = get_shared_bench_config()
    group_name = config.get('virtual_release_group', 'Shared ERPNext')
    
    if frappe.db.exists("Release Group", group_name):
        return group_name
    
    # Get default apps
    default_apps = config.get('default_apps', ['frappe', 'erpnext'])
    
    # Create release group
    rg = frappe.get_doc({
        "doctype": "Release Group",
        "title": group_name,
        "version": config.get('frappe_version', '15'),
        "enabled": 1,
        "is_virtual": 1,
    })
    
    # Add apps
    for app in default_apps:
        rg.append("apps", {
            "app": app,
        })
    
    rg.flags.ignore_links = True
    rg.flags.ignore_mandatory = True
    rg.insert()
    
    frappe.db.commit()
    frappe.logger().info(f"Created virtual release group: {group_name}")
    
    return rg.name


def get_shared_bench_info():
    """
    Get information about the shared bench from Kubernetes.
    
    Returns:
        dict: Shared bench information
    """
    if not is_shared_bench_mode():
        return None
    
    try:
        from press.press.utils.kubernetes import get_shared_bench_manager
        manager = get_shared_bench_manager()
        
        return {
            "namespace": manager.namespace,
            "pod_label": manager.pod_label,
            "sites": manager.list_sites(),
            "status": "Active",
        }
    except Exception as e:
        frappe.log_error(f"Failed to get shared bench info: {e}")
        return {
            "namespace": "unknown",
            "status": "Error",
            "error": str(e),
        }


def cleanup_virtual_resources():
    """
    Clean up virtual server and bench resources.
    
    Use this when disabling shared bench mode.
    """
    # Delete virtual bench
    for bench in frappe.get_all("Bench", filters={"is_virtual": 1}):
        frappe.delete_doc("Bench", bench.name, force=True)
    
    # Delete virtual server
    for server in frappe.get_all("Server", filters={"is_virtual": 1}):
        frappe.delete_doc("Server", server.name, force=True)
    
    # Delete virtual release groups
    for rg in frappe.get_all("Release Group", filters={"is_virtual": 1}):
        frappe.delete_doc("Release Group", rg.name, force=True)
    
    frappe.db.commit()
    frappe.logger().info("Cleaned up virtual resources")
