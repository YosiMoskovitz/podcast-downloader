#!/usr/bin/env python3
"""
Validation script to verify Google Drive credentials and token for production deployment.

This script checks:
1. Credentials file format and structure
2. Token file format and structure  
3. Token validity and refresh capability
4. Google Drive API connectivity
5. Base64 encoding/decoding (simulates production)
"""

import base64
import json
import os
import sys
import pickle
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.google_drive_uploader import GoogleDriveUploader, token_is_valid


def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def check_file_exists(filepath, description):
    """Check if a file exists."""
    if os.path.exists(filepath):
        print(f"✓ {description} found at: {filepath}")
        return True
    else:
        print(f"✗ {description} NOT found at: {filepath}")
        return False


def validate_credentials_structure(creds_data):
    """Validate credentials JSON structure."""
    print("\nValidating credentials structure...")
    
    required_fields = ['client_id', 'project_id', 'auth_uri', 'token_uri', 'client_secret']
    
    # Handle both OAuth client credentials formats
    if 'installed' in creds_data:
        creds_data = creds_data['installed']
        print("  ✓ Credentials use 'installed' wrapper (OAuth desktop app)")
    elif 'web' in creds_data:
        creds_data = creds_data['web']
        print("  ✓ Credentials use 'web' wrapper (OAuth web app)")
    else:
        print("  • Credentials are unwrapped (direct format)")
    
    missing_fields = [field for field in required_fields if field not in creds_data]
    
    if missing_fields:
        print(f"  ✗ Missing required fields: {', '.join(missing_fields)}")
        return False
    else:
        print(f"  ✓ All required fields present")
        print(f"  • Client ID: {creds_data['client_id'][:20]}...")
        print(f"  • Project ID: {creds_data['project_id']}")
        return True


def validate_token_structure(token_data):
    """Validate token JSON structure."""
    print("\nValidating token structure...")
    
    required_fields = ['token', 'refresh_token', 'client_id', 'client_secret']
    
    missing_fields = [field for field in required_fields if field not in token_data]
    
    if missing_fields:
        print(f"  ✗ Missing required fields: {', '.join(missing_fields)}")
        return False
    else:
        print(f"  ✓ All required fields present")
        print(f"  • Has access token: {len(token_data.get('token', '')) > 0}")
        print(f"  • Has refresh token: {len(token_data.get('refresh_token', '')) > 0}")
        return True


def test_base64_encoding(filepath, description):
    """Test base64 encoding/decoding (simulates production)."""
    print(f"\nTesting base64 encoding for {description}...")
    
    try:
        # Try JSON first
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            # Try pickle format for token
            with open(filepath, 'rb') as f:
                creds_obj = pickle.load(f)
            if hasattr(creds_obj, 'to_json'):
                original_data = json.loads(creds_obj.to_json())
            else:
                raise ValueError(f"Unknown file format for {filepath}")
        
        # Encode
        json_str = json.dumps(original_data)
        encoded = base64.b64encode(json_str.encode()).decode()
        print(f"  ✓ Successfully encoded to base64 ({len(encoded)} chars)")
        
        # Decode
        decoded_str = base64.b64decode(encoded).decode('utf-8')
        decoded_data = json.loads(decoded_str)
        print(f"  ✓ Successfully decoded from base64")
        
        # Verify
        if original_data == decoded_data:
            print(f"  ✓ Round-trip encoding/decoding successful")
            return encoded
        else:
            print(f"  ✗ Data mismatch after round-trip")
            return None
            
    except Exception as e:
        print(f"  ✗ Error during base64 encoding: {e}")
        return None


def test_config_loading():
    """Test Config class loading credentials."""
    print("\nTesting Config class credential loading...")
    
    try:
        config = Config()
        
        # Test credentials loading
        try:
            creds = config.get_credentials_json()
            print(f"  ✓ Config successfully loaded credentials")
            print(f"  • Client ID: {creds.get('client_id', 'N/A')[:20]}...")
        except ValueError as e:
            print(f"  ✗ Config failed to load credentials: {e}")
            return False
        
        # Test token loading
        try:
            token = config.get_token_json()
            if token:
                print(f"  ✓ Config successfully loaded token")
                print(f"  • Has refresh token: {bool(token.get('refresh_token'))}")
            else:
                print(f"  ⚠ Config returned None for token (may need OAuth flow)")
        except ValueError as e:
            print(f"  ⚠ Config failed to load token: {e}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error testing Config: {e}")
        return False


def test_token_validity(creds_data, token_data):
    """Test token validity using the token_is_valid function."""
    print("\nTesting token validity and Google Drive API access...")
    
    try:
        is_valid, message = token_is_valid(creds_data, token_data)
        
        if is_valid:
            print(f"  ✓ Token is VALID: {message}")
            return True
        else:
            print(f"  ✗ Token is INVALID: {message}")
            print(f"  • You may need to run: python scripts/auth_gdrive.py")
            return False
            
    except Exception as e:
        print(f"  ✗ Error testing token validity: {e}")
        return False


def test_drive_uploader(creds_data, token_data):
    """Test GoogleDriveUploader initialization."""
    print("\nTesting GoogleDriveUploader initialization...")
    
    try:
        uploader = GoogleDriveUploader(creds_data, token_data)
        print(f"  ✓ GoogleDriveUploader initialized successfully")
        
        # Get updated token (in case it was refreshed)
        updated_token = uploader.get_token_dict()
        print(f"  ✓ Token available for saving")
        
        return True, updated_token
        
    except Exception as e:
        print(f"  ✗ GoogleDriveUploader initialization failed: {e}")
        return False, None


def main():
    print_section("Google Drive Credentials Validation for Production")
    
    # Track validation results
    validations_passed = 0
    total_validations = 0
    
    # 1. Check credentials file
    print_section("Step 1: Check Credentials File")
    creds_path = os.path.join('config', 'credentials.json')
    total_validations += 1
    
    if not check_file_exists(creds_path, "Credentials file"):
        print("\n⚠ Cannot continue without credentials.json")
        print("  Run: python scripts/auth_gdrive.py")
        sys.exit(1)
    
    with open(creds_path, 'r') as f:
        creds_data = json.load(f)
    
    if validate_credentials_structure(creds_data):
        validations_passed += 1
    
    # 2. Check token file
    print_section("Step 2: Check Token File")
    token_path = 'token.json'
    total_validations += 1
    
    if not check_file_exists(token_path, "Token file"):
        print("\n⚠ Cannot continue without token.json")
        print("  Run: python scripts/auth_gdrive.py")
        sys.exit(1)
    
    # Try to load token - could be JSON or pickle format
    try:
        with open(token_path, 'r', encoding='utf-8') as f:
            token_data = json.load(f)
        print("  • Token format: JSON")
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Try pickle format
        try:
            with open(token_path, 'rb') as f:
                creds_obj = pickle.load(f)
            # Convert to JSON format
            if hasattr(creds_obj, 'to_json'):
                token_data = json.loads(creds_obj.to_json())
                print("  • Token format: Pickle (converted to JSON)")
            else:
                print(f"  ✗ Unknown pickle object type: {type(creds_obj)}")
                sys.exit(1)
        except Exception as e:
            print(f"  ✗ Failed to load token: {e}")
            sys.exit(1)
    
    if validate_token_structure(token_data):
        validations_passed += 1
    
    # 3. Test base64 encoding
    print_section("Step 3: Test Base64 Encoding (Production Simulation)")
    total_validations += 2
    
    creds_encoded = test_base64_encoding(creds_path, "credentials")
    if creds_encoded:
        validations_passed += 1
    
    token_encoded = test_base64_encoding(token_path, "token")
    if token_encoded:
        validations_passed += 1
    
    # 4. Test Config class
    print_section("Step 4: Test Config Class Loading")
    total_validations += 1
    
    if test_config_loading():
        validations_passed += 1
    
    # 5. Test token validity
    print_section("Step 5: Test Token Validity & API Access")
    total_validations += 1
    
    # Unwrap credentials if needed
    test_creds = creds_data.get('installed', creds_data.get('web', creds_data))
    
    if test_token_validity(test_creds, token_data):
        validations_passed += 1
    
    # 6. Test GoogleDriveUploader
    print_section("Step 6: Test GoogleDriveUploader")
    total_validations += 1
    
    success, updated_token = test_drive_uploader(test_creds, token_data)
    if success:
        validations_passed += 1
        
        # Check if token was refreshed
        if updated_token and updated_token != token_data:
            print("\n  ⚠ Token was refreshed! You should save the new token:")
            print("    1. The new token is already saved to token.json")
            print("    2. Re-run: python scripts/encode_credentials.py")
            print("    3. Update GOOGLE_TOKEN_BASE64 in production")
    
    # Final summary
    print_section("Validation Summary")
    
    print(f"Validations Passed: {validations_passed}/{total_validations}")
    print()
    
    if validations_passed == total_validations:
        print("✓✓✓ ALL VALIDATIONS PASSED ✓✓✓")
        print()
        print("Your credentials are ready for production deployment!")
        print()
        print("Next steps:")
        print("1. Run: python scripts/encode_credentials.py")
        print("2. Copy the GOOGLE_CREDENTIALS_BASE64 value")
        print("3. Copy the GOOGLE_TOKEN_BASE64 value")
        print("4. Add both to your production environment variables")
        print("5. Ensure DATABASE_URL and SECRET_KEY are also set")
        print()
        print("Production environment variables required:")
        print("  • GOOGLE_CREDENTIALS_BASE64")
        print("  • GOOGLE_TOKEN_BASE64")
        print("  • PODCASTS_CONFIG")
        print("  • DATABASE_URL")
        print("  • SECRET_KEY")
        
    elif validations_passed >= total_validations - 1:
        print("⚠ MOSTLY VALID - Minor issues detected")
        print()
        print("Your credentials should work, but review warnings above.")
        
    else:
        print("✗✗✗ VALIDATION FAILED ✗✗✗")
        print()
        print("Please fix the issues above before deploying to production.")
        print()
        print("Common fixes:")
        print("1. Run: python scripts/auth_gdrive.py")
        print("2. Ensure credentials.json is properly formatted")
        print("3. Check that token has not expired")
    
    print()


if __name__ == "__main__":
    main()
