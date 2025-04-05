#!/usr/bin/env python3
"""
Utility script to generate an access token for the Fyers API.

This script helps users generate an access token for the Fyers API v3,
which is required to use the Market Data Capture Application.

Usage:
    python generate_token.py
"""

import os
import sys
import webbrowser
from urllib.parse import parse_qs, urlparse
import json
from dotenv import load_dotenv
from fyers_apiv3 import fyersModel

def get_input(prompt, default=None):
    """Get input from the user with an optional default value."""
    if default:
        result = input(f"{prompt} [{default}]: ")
        return result if result else default
    else:
        return input(f"{prompt}: ")

def main():
    """Main function to generate a Fyers API access token."""
    print("Fyers API Access Token Generator")
    print("================================")
    
    # Load environment variables
    load_dotenv()
    
    # Get API credentials
    app_id = get_input("Enter your Fyers App ID", os.getenv("FYERS_APP_ID"))
    app_secret = get_input("Enter your Fyers App Secret", os.getenv("FYERS_APP_SECRET"))
    redirect_uri = get_input("Enter your redirect URI", "https://www.google.com/")
    
    if not app_id or not app_secret:
        print("Error: App ID and App Secret are required")
        sys.exit(1)
    
    # Initialize the Fyers API client
    session = fyersModel.SessionModel(
        client_id=app_id,
        secret_key=app_secret,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code"
    )
    
    # Generate the authentication URL
    auth_url = session.generate_authcode()
    print(f"\nPlease visit the following URL to authorize the application:")
    print(auth_url)
    
    # Open the URL in the default browser
    webbrowser.open(auth_url)
    
    # Get the authorization code from the user
    print("\nAfter authorizing, you will be redirected to your redirect URI.")
    print("Please copy the full redirect URL and paste it below:")
    redirect_url = input("Redirect URL: ")
    
    # Extract the auth code from the redirect URL
    parsed_url = urlparse(redirect_url)
    query_params = parse_qs(parsed_url.query)
    
    if "auth_code" not in query_params:
        print("Error: Could not extract auth code from the redirect URL")
        sys.exit(1)
    
    auth_code = query_params["auth_code"][0]
    
    # Generate the access token
    try:
        # In the newer version of the API, generate_token doesn't take auth_code as a parameter
        # Instead, it should be set as an attribute of the session object
        session.set_token(auth_code)
        token_response = session.generate_token()
        
        if not token_response or "access_token" not in token_response:
            print(f"Error generating access token: {token_response}")
            sys.exit(1)
        
        access_token = token_response["access_token"]
        
        print("\nAccess token generated successfully!")
        print(f"Access Token: {access_token}")
        
        # Update the .env file
        update_env = get_input("Do you want to update the .env file with the new token? (y/n)", "y")
        
        if update_env.lower() == "y":
            env_file = ".env"
            
            # Create the .env file if it doesn't exist
            if not os.path.exists(env_file):
                with open(env_file, "w") as f:
                    f.write("# Fyers API Credentials\n")
                    f.write(f"FYERS_APP_ID={app_id}\n")
                    f.write(f"FYERS_APP_SECRET={app_secret}\n")
                    f.write(f"FYERS_ACCESS_TOKEN={access_token}\n")
                    f.write(f"FYERS_USER_ID=\n")
                    f.write("\n# Logging Configuration\n")
                    f.write("LOG_LEVEL=INFO\n")
            else:
                # Read the existing .env file
                with open(env_file, "r") as f:
                    lines = f.readlines()
                
                # Update or add the access token
                token_line_found = False
                with open(env_file, "w") as f:
                    for line in lines:
                        if line.startswith("FYERS_ACCESS_TOKEN="):
                            f.write(f"FYERS_ACCESS_TOKEN={access_token}\n")
                            token_line_found = True
                        else:
                            f.write(line)
                    
                    if not token_line_found:
                        f.write(f"FYERS_ACCESS_TOKEN={access_token}\n")
            
            print(f"Updated {env_file} with the new access token")
        
        # Print instructions for using the token
        print("\nTo use this token with the Market Data Capture Application:")
        print(f"1. Make sure your .env file contains the following line:")
        print(f"   FYERS_ACCESS_TOKEN={access_token}")
        print("2. Run the application with: python main.py")
        
    except Exception as e:
        print(f"Error generating access token: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()