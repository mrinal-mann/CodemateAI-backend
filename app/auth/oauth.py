from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from jose import JWTError, jwt
from typing import Optional, Dict, Any
import logging

from app.config import settings
from app.database import db

logger = logging.getLogger(__name__)


# OAuth 2.0 Scopes
SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/presentations.readonly',
]


class GoogleOAuth:
    """Handle Google OAuth 2.0 authentication."""
    
    def __init__(self):
        self.client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        flow = Flow.from_client_config(
            self.client_config,
            scopes=SCOPES,
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=state
        )
        
        logger.info("Generated OAuth authorization URL")
        return auth_url
    
    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        try:
            flow = Flow.from_client_config(
                self.client_config,
                scopes=SCOPES,
                redirect_uri=settings.GOOGLE_REDIRECT_URI
            )
            
            # Exchange code for tokens
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            # Get user info
            user_info = await self._get_user_info(credentials)
            
            # Store or update user in database
            user = await self._store_user(user_info, credentials)
            
            # Generate JWT token
            jwt_token = self._create_jwt_token(user.id)
            
            logger.info(f"User authenticated: {user.email}")
            
            return {
                "access_token": jwt_token,
                "user": user,
                "google_tokens": {
                    "access_token": credentials.token,
                    "refresh_token": credentials.refresh_token,
                }
            }
            
        except Exception as e:
            logger.error(f"OAuth token exchange failed: {str(e)}")
            raise
    
    async def _get_user_info(self, credentials: Credentials) -> Dict[str, Any]:
        try:
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            
            return {
                "google_id": user_info.get("id"),
                "email": user_info.get("email"),
                "name": user_info.get("name"),
                "avatar": user_info.get("picture"),
            }
        except Exception as e:
            logger.error(f"Failed to get user info: {str(e)}")
            raise
    
    async def _store_user(self, user_info: Dict[str, Any], credentials: Credentials):
        try:
            # Check if user exists
            user = await db.user.find_unique(
                where={"googleId": user_info["google_id"]}
            )
            
            if user:
                # Update existing user
                user = await db.user.update(
                    where={"id": user.id},
                    data={
                        "name": user_info.get("name"),
                        "avatar": user_info.get("avatar"),
                        "accessToken": credentials.token,
                        "refreshToken": credentials.refresh_token,
                        "updatedAt": datetime.now(),
                    }
                )
                logger.info(f"Updated user: {user.email}")
            else:
                # Create new user
                user = await db.user.create(
                    data={
                        "googleId": user_info["google_id"],
                        "email": user_info["email"],
                        "name": user_info.get("name"),
                        "avatar": user_info.get("avatar"),
                        "accessToken": credentials.token,
                        "refreshToken": credentials.refresh_token,
                    }
                )
                logger.info(f"Created new user: {user.email}")
            
            return user
            
        except Exception as e:
            logger.error(f"Failed to store user: {str(e)}")
            raise
    
    def _create_jwt_token(self, user_id: str) -> str:
        expires_delta = timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
        expire = datetime.utcnow() + expires_delta
        
        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.utcnow(),
        }
        
        token = jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
        
        return token
    
    def verify_jwt_token(self, token: str) -> Optional[str]:
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            user_id: str = payload.get("sub")
            return user_id
        except JWTError as e:
            logger.error(f"JWT verification failed: {str(e)}")
            return None
    
    async def refresh_google_tokens(self, user_id: str) -> Credentials:
        try:
            user = await db.user.find_unique(where={"id": user_id})
            
            if not user or not user.refreshToken:
                raise ValueError("User not found or no refresh token")
            
            credentials = Credentials(
                token=user.accessToken,
                refresh_token=user.refreshToken,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
            )
            
            # Refresh if expired
            if credentials.expired:
                from google.auth.transport.requests import Request
                credentials.refresh(Request())
                
                # Update tokens in database
                await db.user.update(
                    where={"id": user_id},
                    data={
                        "accessToken": credentials.token,
                        "refreshToken": credentials.refresh_token,
                    }
                )
                
                logger.info(f"Refreshed tokens for user: {user.email}")
            
            return credentials
            
        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            raise


# Create global OAuth instance
google_oauth = GoogleOAuth()