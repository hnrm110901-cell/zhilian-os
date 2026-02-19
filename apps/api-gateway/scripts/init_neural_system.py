"""
Neural System Initialization Script
Initializes Qdrant collections for the neural system
"""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
import structlog

logger = structlog.get_logger()


def initialize_qdrant_collections():
    """Initialize Qdrant collections for neural system"""

    # Configuration
    QDRANT_HOST = "localhost"
    QDRANT_PORT = 6333
    EMBEDDING_DIMENSION = 384

    try:
        # Connect to Qdrant
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        logger.info("Connected to Qdrant", host=QDRANT_HOST, port=QDRANT_PORT)

        # Define collections
        collections = {
            "orders": "订单数据集合",
            "dishes": "菜品数据集合",
            "staff": "员工数据集合",
            "events": "事件数据集合"
        }

        # Create collections
        for collection_name, description in collections.items():
            try:
                # Check if collection exists
                existing_collections = client.get_collections().collections
                collection_exists = any(c.name == collection_name for c in existing_collections)

                if collection_exists:
                    logger.info(f"Collection already exists", collection=collection_name)
                else:
                    # Create collection
                    client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(
                            size=EMBEDDING_DIMENSION,
                            distance=Distance.COSINE
                        )
                    )
                    logger.info(f"Created collection", collection=collection_name, description=description)

            except Exception as e:
                logger.error(f"Failed to create collection", collection=collection_name, error=str(e))
                raise

        # Verify collections
        collections_info = client.get_collections()
        logger.info("Qdrant collections initialized successfully")
        logger.info(f"Total collections: {len(collections_info.collections)}")

        for collection in collections_info.collections:
            logger.info(f"  - {collection.name}: {collection.vectors_count} vectors")

        return True

    except Exception as e:
        logger.error("Failed to initialize Qdrant collections", error=str(e))
        return False


def main():
    """Main function"""
    logger.info("Starting neural system initialization...")

    success = initialize_qdrant_collections()

    if success:
        logger.info("✓ Neural system initialized successfully!")
        logger.info("You can now start using the neural system API")
    else:
        logger.error("✗ Neural system initialization failed")
        logger.error("Please check Qdrant connection and try again")


if __name__ == "__main__":
    main()
