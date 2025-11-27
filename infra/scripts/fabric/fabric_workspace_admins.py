#!/usr/bin/env python3
"""
Fabric Workspace Administrators Management Module

This module provides functionality to add administrators to a Microsoft Fabric workspace.
Supports both user principal names (UPNs) and service principal object IDs.

Features:
- Add administrators by UPN (user@contoso.com) with Graph API resolution
- Add administrators by object ID with fallback logic for User/ServicePrincipal types
- Skip existing administrators to avoid duplicates
- Comprehensive error handling and reporting
- Support for both individual users and service principals

Usage:
    python fabric_workspace_admins.py --workspace-id "12345678-1234-1234-1234-123456789012" --fabricAdmins user@contoso.com admin@company.com
    python fabric_workspace_admins.py --workspace-id "12345678-1234-1234-1234-123456789012" --fabricAdminsByObjectId 12345678-1234-1234-1234-123456789012

Requirements:
    - fabric_api.py module in the same directory
    - graph_api.py module in the same directory
    - Azure CLI authentication or other Azure credentials configured
    - Appropriate Fabric workspace permissions (Admin role required to add other administrators)
"""

import argparse
import sys
import uuid
from fabric_api import FabricApiClient, FabricWorkspaceApiClient, FabricApiError
from graph_api import create_graph_client, GraphApiError

####################
# Helper Functions #
####################

def is_valid_guid(value):
    """Check if a string is a valid GUID format."""
    if not value or not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False

def detect_principal_type(admin_identifier, graph_client=None):
    """
    Detect if an identifier is a user or service principal and resolve to object ID.
    
    Args:
        admin_identifier: User UPN, object ID (GUID), or application ID (GUID)
        graph_client: Optional Graph API client (will create one if not provided)
    
    Returns:
        Tuple of (principal_type, object_id, principal_data)
        - principal_type: "User" or "ServicePrincipal" 
        - object_id: The object ID of the principal
        - principal_data: Full principal object from Graph API
        
    Raises:
        ValueError: If identifier cannot be resolved
        GraphApiError: If Graph API calls fail
    """
    try:
        # Create Graph client if not provided
        if graph_client is None:
            graph_client = create_graph_client()
        
        # Use Graph API to resolve the principal
        principal_type, object_id, principal_data = graph_client.resolve_principal(admin_identifier)
        
        return principal_type, object_id, principal_data
        
    except GraphApiError as e:
        # Convert Graph API errors to ValueError for backward compatibility
        raise ValueError(f"Unable to resolve principal '{admin_identifier}': {str(e)}")
    except Exception as e:
        # Fallback to original logic if Graph API is not available
        print(f"  ⚠️ WARNING: Graph API lookup failed for '{admin_identifier}': {str(e)}")
        print(f"     Falling back to basic identifier pattern detection...")
        
        if is_valid_guid(admin_identifier):
            return "ServicePrincipal", admin_identifier, {"id": admin_identifier, "displayName": "Unknown"}
        elif "@" in admin_identifier and "." in admin_identifier:
            return "User", admin_identifier, {"userPrincipalName": admin_identifier, "displayName": "Unknown"}
        else:
            raise ValueError(
                f"Unable to determine if '{admin_identifier}' is a user UPN or service principal GUID")

def get_existing_admin_principals(workspace_client):
    """Get set of existing admin principal IDs for duplicate checking."""
    try:
        print(f"    🔍 Checking existing role assignments...")
        assignments = workspace_client.get_role_assignments(get_all=True)
        
        existing_principals = set()
        admin_count = 0
        
        for assignment in assignments:
            if assignment.get('role') == 'Admin':
                admin_count += 1
                principal = assignment.get('principal', {})
                principal_id = principal.get('id', '').lower()
                if principal_id:
                    existing_principals.add(principal_id)
                
                # Also add UPN if available for easier matching
                user_details = principal.get('userDetails', {})
                upn = user_details.get('userPrincipalName', '').lower()
                if upn:
                    existing_principals.add(upn)
        
        print(f"    📊 Found {admin_count} existing administrator(s)")
        return existing_principals
        
    except Exception as e:
        print(f"    ⚠️ WARNING: Could not retrieve existing role assignments: {str(e)}")
        print("       Will proceed but may create duplicates")
        return set()

def add_workspace_admin(workspace_client, admin_identifier, existing_principals, graph_client):
    """Add a single workspace administrator with simplified error handling."""
    # Check if already exists
    if admin_identifier.lower() in existing_principals:
        print(f"    ⏭️ Skipping '{admin_identifier}' - already a workspace administrator")
        return {'status': 'skipped', 'message': 'Already exists'}
    
    try:
        # Try to resolve principal type using Graph API
        principal_type, object_id, principal_data = detect_principal_type(admin_identifier, graph_client)
        
        if object_id.lower() in existing_principals:
            print(f"    ⏭️ Skipping '{admin_identifier}' - already a workspace administrator")
            existing_principals.add(admin_identifier.lower())  # Prevent future duplicates
            return {'status': 'skipped', 'message': 'Already exists (by object ID)'}
        
        display_name = principal_data.get('displayName', 'Unknown')
        print(f"    🔐 Adding {principal_type.lower()} administrator: {admin_identifier} ({display_name})")
        
        # Add role assignment based on type
        if principal_type == "User":
            workspace_client.add_role_assignment(
                principal_id=object_id,
                principal_type=principal_type,
                role="Admin",
                display_name=display_name,
                user_principal_name=principal_data.get('userPrincipalName', admin_identifier)
            )
        else:  # ServicePrincipal
            workspace_client.add_role_assignment(
                principal_id=object_id,
                principal_type=principal_type,
                role="Admin",
                display_name=display_name,
                aad_app_id=principal_data.get('appId')
            )
        
        print(f"    ✅ Successfully added '{admin_identifier}' as workspace administrator")
        existing_principals.add(object_id.lower())
        existing_principals.add(admin_identifier.lower())
        return {'status': 'success', 'message': 'Added successfully'}
        
    except (ValueError, GraphApiError) as e:
        return {'status': 'failed', 'message': f'Principal type detection failed: {str(e)}'}
        
    except FabricApiError as e:
        error_hints = {
            400: "Verify the identifier is correct and the principal exists",
            403: "Ensure you have Admin permissions on this workspace", 
            404: "Check if the principal exists in your Azure AD tenant"
        }
        hint = error_hints.get(e.status_code, "Check API permissions and principal validity")
        return {'status': 'failed', 'message': f'API error ({e.status_code}): {hint}'}
        
    except Exception as e:
        return {'status': 'failed', 'message': f'Unexpected error: {str(e)}'}

def add_workspace_admin_by_object_id(workspace_client, object_id, existing_principals):
    """Add workspace administrator by object ID using fallback logic to try both User and ServicePrincipal types."""
    # Check if already exists
    if object_id.lower() in existing_principals:
        print(f"    ⏭️ Skipping '{object_id}' - already a workspace administrator")
        return {'status': 'skipped', 'message': 'Already exists'}
    
    print(f"    🔐 Adding administrator by Object ID: {object_id}")
    print(f"       Will try both User and ServicePrincipal types...")
    
    # Try both User and ServicePrincipal types
    for principal_type in ["User", "ServicePrincipal"]:
        try:
            print(f"       Trying as {principal_type}...")
            workspace_client.add_role_assignment(
                principal_id=object_id,
                principal_type=principal_type,
                role="Admin"
            )
            print(f"    ✅ Successfully added '{object_id}' as workspace administrator ({principal_type})")
            existing_principals.add(object_id.lower())
            return {'status': 'success', 'message': f'Added successfully as {principal_type}'}
        except FabricApiError as e:
            print(f"       Failed as {principal_type}: {str(e)}")
        except Exception as e:
            print(f"       Unexpected error as {principal_type}: {str(e)}")
    
    return {'status': 'failed', 'message': 'Failed to add as both User and ServicePrincipal types'}

def setup_workspace_administrators(workspace_client: FabricWorkspaceApiClient, workspace_id: str, fabric_admins_csv: str = None, fabric_admins: list = None, fabric_admins_by_object_id: list = None) -> dict:
    """
    Add administrators to a Microsoft Fabric workspace.
    
    Args:
        workspace_client: Authenticated FabricWorkspaceApiClient instance
        workspace_id: ID of the workspace to add administrators to
        fabric_admins_csv: Comma-separated string of administrators (UPNs or GUIDs) - primary input method
        fabric_admins: List of administrators to add (UPNs or object IDs with Graph API resolution) - legacy support
        fabric_admins_by_object_id: List of object IDs to add as administrators (with fallback logic) - legacy support
        
    Returns:
        Dict with operation results including counts of added, skipped, and failed assignments
    """
    # Parse comma-separated input if provided
    parsed_admins = []
    if fabric_admins_csv:
        # Split by comma and clean up whitespace
        parsed_admins = [admin.strip() for admin in fabric_admins_csv.split(',') if admin.strip()]
        print(f"📋 Parsed {len(parsed_admins)} administrator(s) from comma-separated input: {', '.join(parsed_admins)}")
    
    # Combine with legacy list inputs for backward compatibility
    all_fabric_admins = parsed_admins + (fabric_admins or [])
    
    if not all_fabric_admins and not fabric_admins_by_object_id:
        print("ℹ️ No administrators specified - skipping workspace administrator setup")
        return {'added': 0, 'skipped': 0, 'failed': 0, 'errors': []}
    
    print(f"👥 Setting up workspace administrators...")
    
    # Initialize Graph API client
    try:
        graph_client = create_graph_client()
        print("✅ Graph API client authenticated successfully")
    except Exception as e:
        print(f"❌ WARNING: Failed to authenticate with Graph APIs: {str(e)}")
        graph_client = None
    
    # Get existing admin principals for this workspace
    existing_admin_principals = get_existing_admin_principals(workspace_client)
    
    workspace_stats = {'added': 0, 'skipped': 0, 'failed': 0, 'errors': []}
    
    # Phase 1: Process fabricAdmins (UPNs and object IDs with Graph API resolution)
    if all_fabric_admins:
        print(f"    👥 Adding fabricAdmins...")
        
        for admin_identifier in all_fabric_admins:
            result = add_workspace_admin(workspace_client, admin_identifier, existing_admin_principals, graph_client)
            
            if result['status'] == 'success':
                workspace_stats['added'] += 1
            elif result['status'] == 'skipped':
                workspace_stats['skipped'] += 1
            else:  # failed
                workspace_stats['failed'] += 1
                workspace_stats['errors'].append(f"{admin_identifier}: {result['message']}")
    
    # Phase 2: Process fabricAdminsByObjectId (Object IDs with fallback logic)
    if fabric_admins_by_object_id:
        print(f"    👥 Adding fabricAdminsByObjectId...")
        
        for object_id in fabric_admins_by_object_id:
            result = add_workspace_admin_by_object_id(workspace_client, object_id, existing_admin_principals)
            
            if result['status'] == 'success':
                workspace_stats['added'] += 1
            elif result['status'] == 'skipped':
                workspace_stats['skipped'] += 1
            else:  # failed
                workspace_stats['failed'] += 1
                workspace_stats['errors'].append(f"{object_id}: {result['message']}")
    
    # Print workspace summary
    total_requested = len(all_fabric_admins or []) + len(fabric_admins_by_object_id or [])
    print(f"    📊 Workspace administrators summary - Added: {workspace_stats['added']}, Skipped: {workspace_stats['skipped']}, Failed: {workspace_stats['failed']}, Total: {total_requested}")
    
    # Show error details if any failures occurred
    if workspace_stats['errors']:
        print(f"    ⚠️ Errors in workspace administrator setup:")
        for error in workspace_stats['errors'][:3]:  # Show first 3 errors
            print(f"       • {error}")
        if len(workspace_stats['errors']) > 3:
            print(f"       ... and {len(workspace_stats['errors']) - 3} more error(s)")
    
    if workspace_stats['added'] > 0 or workspace_stats['skipped'] > 0:
        return workspace_stats
    elif workspace_stats['failed'] > 0:
        print(f"❌ Failed to add workspace administrators")
        return None
    else:
        print(f"✅ No administrators to add")
        return workspace_stats

##########################
# Command line arguments #
##########################

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Add administrators to a Microsoft Fabric workspace')
    parser.add_argument('--workspace-id', required=True,
                        help='ID of the workspace to add administrators to')
    parser.add_argument('--fabricAdmins-csv',
                        help='Comma-separated list of administrators (UPNs or GUIDs). Example: user1@contoso.com,user2@contoso.com,12345678-1234-1234-1234-123456789012')
    parser.add_argument('--fabricAdmins', nargs='*', default=[],
                        help='List of administrators to add. Can include user principal names (UPNs) like user@contoso.com or service principal IDs (GUIDs) like 12345678-1234-1234-1234-123456789012')
    parser.add_argument('--fabricAdminsByObjectId', nargs='*', default=[],
                        help='List of object IDs (GUIDs) to add as workspace administrators. These will be tried as both User and ServicePrincipal types. Format: 12345678-1234-1234-1234-123456789012')
    args = parser.parse_args()

    # Check if at least one admin type is provided
    if not args.fabricAdmins_csv and not args.fabricAdmins and not args.fabricAdminsByObjectId:
        print("❌ ERROR: At least one of --fabricAdmins-csv, --fabricAdmins or --fabricAdminsByObjectId must be provided")
        parser.print_help()
        sys.exit(1)

    print(f"🚀 Starting Microsoft Fabric workspace administrator management")
    print(f"📁 Workspace ID: {args.workspace_id}")
    if args.fabricAdmins_csv:
        print(f"📋 Administrators (CSV): {args.fabricAdmins_csv}")
    if args.fabricAdmins:
        print(f"📋 Administrators to add: {', '.join(args.fabricAdmins)}")
    if args.fabricAdminsByObjectId:
        print(f"📋 Administrators to add by Object ID: {', '.join(args.fabricAdminsByObjectId)}")
    print("-" * 60)

    # Initialize Fabric API clients
    try:
        from fabric_auth import authenticate_workspace
    
        workspace_client = authenticate_workspace(args.workspace_id)
        if not workspace_client:
            print("❌ Failed to authenticate workspace-specific Fabric API client")
            sys.exit(1)
        print("✅ Fabric Workspace API client authenticated successfully")
    except Exception as e:
        print(f"❌ ERROR: Failed to authenticate with Fabric APIs")
        print(f"   Details: {str(e)}")
        print("   Solution: Please ensure you are logged in with Azure CLI: az login")
        sys.exit(1)

    # Setup workspace administrators
    result = setup_workspace_administrators(
        workspace_client=workspace_client,
        workspace_id=args.workspace_id,
        fabric_admins_csv=args.fabricAdmins_csv,
        fabric_admins=args.fabricAdmins if args.fabricAdmins else None,
        fabric_admins_by_object_id=args.fabricAdminsByObjectId if args.fabricAdminsByObjectId else None
    )

    if result is None:
        print("❌ Failed to setup workspace administrators")
        sys.exit(1)
    else:
        print(f"✅ Workspace administrator setup completed!")
        print(f"📊 Summary: Added {result['added']}, Skipped {result['skipped']}, Failed {result['failed']}")
        sys.exit(0)

if __name__ == "__main__":
    main()