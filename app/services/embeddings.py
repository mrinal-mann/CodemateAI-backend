from langchain_google_genai import GoogleGenerativeAIEmbeddings
from typing import List
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    
    def __init__(self):
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=settings.GOOGLE_API_KEY
        )
        logger.info("Initialized Google text-embedding-004")
    
    async def embed_text(self, text: str) -> List[float]:
        try:
            embedding = await self.embeddings.aembed_query(text)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {str(e)}")
            raise
    
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        try:
            embeddings = await self.embeddings.aembed_documents(texts)
            logger.info(f"Generated embeddings for {len(texts)} texts")
            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {str(e)}")
            raise
    
    def get_embedding_dimension(self) -> int:
        return 768