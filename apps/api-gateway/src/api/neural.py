"""
Neural System API
Provides REST API access to Zhilian OS neural system capabilities
"""
import os
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from ..services.neural_system import NeuralSystemOrchestrator
from ..schemas.restaurant_standard_schema import (
    NeuralEventSchema,
    OrderSchema,
    DishSchema,
    StaffSchema
)

router = APIRouter()
neural_system = NeuralSystemOrchestrator()


# Request/Response Models
class EventEmissionRequest(BaseModel):
    """Request to emit a neural event"""
    event_type: str = Field(..., description="Event type (order, dish, staff, payment, inventory)")
    store_id: str = Field(..., description="Store identifier")
    data: Dict[str, Any] = Field(..., description="Event data")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class EventEmissionResponse(BaseModel):
    """Response after emitting event"""
    success: bool
    event_id: str
    message: str


class SemanticSearchRequest(BaseModel):
    """Request for semantic search"""
    query: str = Field(..., description="Search query text")
    store_id: str = Field(..., description="Store identifier for data isolation")
    top_k: int = Field(default=int(os.getenv("NEURAL_SEARCH_TOP_K", "10")), ge=1, le=100, description="Number of results to return")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Additional filters")


class SemanticSearchResult(BaseModel):
    """Single search result"""
    id: str
    score: float
    data: Dict[str, Any]


class SemanticSearchResponse(BaseModel):
    """Response from semantic search"""
    query: str
    results: List[SemanticSearchResult]
    total: int


class FederatedLearningParticipationRequest(BaseModel):
    """Request to participate in federated learning"""
    store_id: str = Field(..., description="Store identifier")
    local_model_path: str = Field(..., description="Path to local model file")
    training_samples: int = Field(..., ge=1, description="Number of training samples")
    metrics: Optional[Dict[str, float]] = Field(default=None, description="Training metrics")


class FederatedLearningParticipationResponse(BaseModel):
    """Response after federated learning participation"""
    success: bool
    round_number: int
    message: str


class SystemStatusResponse(BaseModel):
    """Neural system status"""
    status: str
    total_events: int
    total_stores: int
    federated_learning_round: int
    vector_db_collections: Dict[str, int]
    uptime_seconds: float


# API Endpoints

@router.post("/events/emit", response_model=EventEmissionResponse)
async def emit_event(request: EventEmissionRequest):
    """
    Emit a neural event to the system

    The event will be:
    1. Processed by the appropriate handler
    2. Indexed in the vector database
    3. Distributed to relevant subscribers
    """
    try:
        await neural_system.emit_event(
            event_type=request.event_type,
            event_source="api",
            data=request.data,
            store_id=request.store_id,
            priority=0
        )

        event_id = f"{request.event_type}_{request.store_id}_{datetime.now().timestamp()}"

        return EventEmissionResponse(
            success=True,
            event_id=event_id,
            message=f"Event {request.event_type} emitted successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to emit event: {str(e)}")


@router.post("/search/orders", response_model=SemanticSearchResponse)
async def search_orders(request: SemanticSearchRequest):
    """
    Semantic search for orders

    Uses vector embeddings to find orders matching the query.
    Data isolation ensures only orders from the specified store are returned.
    """
    try:
        results = await neural_system.semantic_search_orders(
            query=request.query,
            store_id=request.store_id,
            limit=request.top_k
        )

        search_results = [
            SemanticSearchResult(
                id=result["id"],
                score=result["score"],
                data=result["payload"]
            )
            for result in results
        ]

        return SemanticSearchResponse(
            query=request.query,
            results=search_results,
            total=len(search_results)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/search/dishes", response_model=SemanticSearchResponse)
async def search_dishes(request: SemanticSearchRequest):
    """
    Semantic search for dishes

    Uses vector embeddings to find dishes matching the query.
    Useful for menu recommendations, ingredient searches, etc.
    """
    try:
        results = await neural_system.semantic_search_dishes(
            query=request.query,
            store_id=request.store_id,
            limit=request.top_k
        )

        search_results = [
            SemanticSearchResult(
                id=result["id"],
                score=result["score"],
                data=result["payload"]
            )
            for result in results
        ]

        return SemanticSearchResponse(
            query=request.query,
            results=search_results,
            total=len(search_results)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/search/events", response_model=SemanticSearchResponse)
async def search_events(request: SemanticSearchRequest):
    """
    Semantic search for historical events

    Search through event history to find patterns, anomalies, or specific incidents.
    """
    try:
        results = await neural_system.semantic_search_events(
            query=request.query,
            store_id=request.store_id,
            limit=request.top_k
        )

        search_results = [
            SemanticSearchResult(
                id=result["id"],
                score=result["score"],
                data=result["payload"]
            )
            for result in results
        ]

        return SemanticSearchResponse(
            query=request.query,
            results=search_results,
            total=len(search_results)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/federated-learning/participate", response_model=FederatedLearningParticipationResponse)
async def participate_in_federated_learning(request: FederatedLearningParticipationRequest):
    """
    Participate in federated learning round

    Upload local model updates to contribute to global model improvement
    while keeping raw data isolated at the store level.
    """
    try:
        result = await neural_system.participate_in_federated_learning(
            store_id=request.store_id,
            model_type="demand_prediction"  # Default model type
        )

        return FederatedLearningParticipationResponse(
            success=result.get("success", False),
            round_number=result.get("round", 0),
            message=result.get("message", "Participated in federated learning")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Participation failed: {str(e)}")


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status():
    """
    Get neural system status

    Returns overall system health, statistics, and operational metrics.
    """
    try:
        # Get statistics from various components
        vector_db_stats = {
            "orders": 0,  # Would query actual collection sizes
            "dishes": 0,
            "staff": 0,
            "events": 0
        }

        return SystemStatusResponse(
            status="operational",
            total_events=len(neural_system.event_queue),
            total_stores=0,  # Removed federated learning
            federated_learning_round=0,  # Removed federated learning
            vector_db_collections=vector_db_stats,
            uptime_seconds=0.0  # Would calculate actual uptime
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get("/health")
async def health_check():
    """
    Health check endpoint

    Simple endpoint to verify the neural system is responsive.
    """
    return {
        "status": "healthy",
        "service": "neural_system",
        "timestamp": datetime.now().isoformat()
    }


# ==================== Batch Indexing Endpoints ====================

class BatchIndexOrdersRequest(BaseModel):
    """Request to batch index orders"""
    orders: List[Dict[str, Any]] = Field(..., description="List of orders to index", min_items=1, max_items=1000)


class BatchIndexDishesRequest(BaseModel):
    """Request to batch index dishes"""
    dishes: List[Dict[str, Any]] = Field(..., description="List of dishes to index", min_items=1, max_items=1000)


class BatchIndexEventsRequest(BaseModel):
    """Request to batch index events"""
    events: List[Dict[str, Any]] = Field(..., description="List of events to index", min_items=1, max_items=1000)


class BatchIndexResponse(BaseModel):
    """Response from batch indexing operation"""
    success: bool = Field(..., description="Overall operation success")
    total: int = Field(..., description="Total items submitted")
    indexed: int = Field(..., description="Successfully indexed items")
    failed: int = Field(..., description="Failed items")
    errors: List[str] = Field(default_factory=list, description="Error messages (max 10)")
    duration_seconds: float = Field(..., description="Operation duration in seconds")


@router.post("/batch/index/orders", response_model=BatchIndexResponse)
async def batch_index_orders(request: BatchIndexOrdersRequest):
    """
    Batch index multiple orders

    Efficiently index multiple orders in a single operation.
    Supports up to 1000 orders per request.

    Returns statistics about the indexing operation including:
    - Total items processed
    - Successfully indexed count
    - Failed count with error details
    - Operation duration
    """
    try:
        from ..services.vector_db_service_enhanced import vector_db_service_enhanced

        # Ensure service is initialized
        if not vector_db_service_enhanced._initialized:
            await vector_db_service_enhanced.initialize()

        # Perform batch indexing
        result = await vector_db_service_enhanced.index_orders_batch(request.orders)

        return BatchIndexResponse(
            success=result["success"] >= result["total"] * 0.8,  # 80% success threshold
            total=result["total"],
            indexed=result["success"],
            failed=result["failure"],
            errors=result["errors"],
            duration_seconds=result["duration_seconds"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch indexing failed: {str(e)}")


@router.post("/batch/index/dishes", response_model=BatchIndexResponse)
async def batch_index_dishes(request: BatchIndexDishesRequest):
    """
    Batch index multiple dishes

    Efficiently index multiple dishes in a single operation.
    Supports up to 1000 dishes per request.
    """
    try:
        from ..services.vector_db_service_enhanced import vector_db_service_enhanced

        if not vector_db_service_enhanced._initialized:
            await vector_db_service_enhanced.initialize()

        # Perform batch indexing for dishes
        result = await vector_db_service_enhanced.index_dishes_batch(request.dishes)

        return BatchIndexResponse(
            success=result["success"] >= result["total"] * 0.8,
            total=result["total"],
            indexed=result["success"],
            failed=result["failure"],
            errors=result["errors"],
            duration_seconds=result["duration_seconds"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch indexing failed: {str(e)}")


@router.post("/batch/index/events", response_model=BatchIndexResponse)
async def batch_index_events(request: BatchIndexEventsRequest):
    """
    Batch index multiple events

    Efficiently index multiple events in a single operation.
    Supports up to 1000 events per request.
    """
    try:
        from ..services.vector_db_service_enhanced import vector_db_service_enhanced

        if not vector_db_service_enhanced._initialized:
            await vector_db_service_enhanced.initialize()

        # Perform batch indexing for events
        result = await vector_db_service_enhanced.index_events_batch(request.events)

        return BatchIndexResponse(
            success=result["success"] >= result["total"] * 0.8,
            total=result["total"],
            indexed=result["success"],
            failed=result["failure"],
            errors=result["errors"],
            duration_seconds=result["duration_seconds"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch indexing failed: {str(e)}")

