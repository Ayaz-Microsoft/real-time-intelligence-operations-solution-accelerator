#!/usr/bin/env python3
"""
Fabric Authentication Module

This module provides authentication functionality for Microsoft Fabric API operations.

Usage:
    python fabric_auth.py

Requirements:
    - fabric_api.py module in the same directory
    - Azure CLI authentication or other Azure credentials configured
"""

import argparse
import sys
from fabric_api import FabricApiClient, FabricWorkspaceApiClient

def authenticate():
    """
    Authenticate and create Fabric API client.
    
    Returns:
        Authenticated FabricApiClient instance if successful, None if failed
    """
    try:
        result = FabricApiClient()
        print(f"✅ Successfully authenticated Fabric API client")
        return result
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def authenticate_workspace(workspace_id: str):
    """
    Authenticate and create Fabric Workspace API client for a specific workspace.
    
    Args:
        workspace_id: ID of the workspace to create client for
        
    Returns:
        Authenticated FabricWorkspaceApiClient instance if successful, None if failed
    """
    try:
        result = FabricWorkspaceApiClient(workspace_id=workspace_id)
        print(f"✅ Successfully authenticated Fabric Workspace API client for workspace: {workspace_id}")
        return result
    except Exception as e:
        print(f"❌ Error creating workspace client: {e}")
        return None

def main():
    """Main function to handle command line arguments and execute authentication."""
    parser = argparse.ArgumentParser(
        description="Test Fabric API authentication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fabric_auth.py
  python fabric_auth.py --workspace-id "12345678-1234-1234-1234-123456789012"
        """
    )
    
    parser.add_argument(
        "--workspace-id",
        help="Optional workspace ID to test workspace-specific authentication"
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Execute the main logic
    result = authenticate()
    print(f"\n✅ Base Authentication: {'Success' if result else 'Failed'}")
    
    if args.workspace_id and result:
        workspace_result = authenticate_workspace(args.workspace_id)
        print(f"✅ Workspace Authentication: {'Success' if workspace_result else 'Failed'}")


if __name__ == "__main__":
    main()