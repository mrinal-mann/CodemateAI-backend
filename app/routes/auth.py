
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
import logging

from app.models import (
    GoogleAuthURL,
    GoogleAuthCallback,
    TokenResponse,
    UserResponse,
    ErrorResponse
)
from app.auth.oauth import google_oauth
from app.auth.middleware import get_current_user
from app.config import settings
from prisma.models import User  # pyright: ignore[reportMissingImports]

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/google/login",
    response_model=GoogleAuthURL,
    summary="Get Google OAuth URL",
    description="Generate Google OAuth authorization URL for user login"
)
async def google_login():
    try:
        auth_url = google_oauth.get_authorization_url()
        logger.info("Generated Google OAuth URL")
        
        return GoogleAuthURL(auth_url=auth_url)
        
    except Exception as e:
        logger.error(f"Failed to generate OAuth URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authorization URL"
        )


@router.post(
    "/google/callback",
    response_model=TokenResponse,
    summary="Google OAuth Callback",
    description="Handle Google OAuth callback and exchange code for tokens"
)
async def google_callback(callback_data: GoogleAuthCallback):
    try:
        # Exchange code for tokens
        result = await google_oauth.exchange_code_for_tokens(callback_data.code)
        
        logger.info(f"User authenticated: {result['user'].email}")
        
        return TokenResponse(
            access_token=result["access_token"],
            token_type="bearer",
            user=UserResponse.model_validate(result["user"])
        )
        
    except ValueError as e:
        logger.error(f"OAuth callback validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"OAuth callback failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get Current User",
    description="Get currently authenticated user information"
)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.post(
    "/logout",
    summary="Logout User",
    description="Logout current user (client should delete token)"
)
async def logout(current_user: User = Depends(get_current_user)):
    logger.info(f"User logged out: {current_user.email}")
    
    return {
        "message": "Logged out successfully",
        "user_id": current_user.id
    }