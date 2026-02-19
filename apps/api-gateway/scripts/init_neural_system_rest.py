"""
Neural System Initialization Script (REST API version)
Initializes Qdrant collections for the neural system using REST API
"""
import requests
import structlog

logger = structlog.get_logger()


def initialize_qdrant_collections():
    """Initialize Qdrant collections for neural system"""

    # Configuration
    QDRANT_URL = "http://localhost:6333"
    EMBEDDING_DIMENSION = 384

    try:
        logger.info("Starting neural system initialization...")
        logger.info("Connecting to Qdrant", url=QDRANT_URL)

        # Define collections
        collections = {
            "orders": "订单数据集合",
            "dishes": "菜品数据集合",
            "staff": "员工数据集合",
            "events": "事件数据集合"
        }

        # Get existing collections
        response = requests.get(f"{QDRANT_URL}/collections")
        response.raise_for_status()
        existing_collections = [c["name"] for c in response.json()["result"]["collections"]]
        logger.info(f"Found {len(existing_collections)} existing collections")

        # Create collections
        for collection_name, description in collections.items():
            if collection_name in existing_collections:
                logger.info(f"Collection already exists", collection=collection_name)
            else:
                # Create collection
                payload = {
                    "vectors": {
                        "size": EMBEDDING_DIMENSION,
                        "distance": "Cosine"
                    }
                }
                response = requests.put(
                    f"{QDRANT_URL}/collections/{collection_name}",
                    json=payload
                )
                response.raise_for_status()
                logger.info(f"Created collection", collection=collection_name, description=description)

        # Verify collections
        response = requests.get(f"{QDRANT_URL}/collections")
        response.raise_for_status()
        collections_info = response.json()["result"]["collections"]

        logger.info("✓ Qdrant collections initialized successfully!")
        logger.info(f"Total collections: {len(collections_info)}")

        for collection in collections_info:
            logger.info(f"  - {collection['name']}: {collection.get('vectors_count', 0)} vectors")

        logger.info("You can now start using the neural system API")
        return True

    except Exception as e:
        logger.error("✗ Neural system initialization failed", error=str(e))
        logger.error("Please check Qdrant connection and try again")
        return False


if __name__ == "__main__":
    initialize_qdrant_collections()
