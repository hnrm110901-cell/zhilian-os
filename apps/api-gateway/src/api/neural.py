"""
Neural System API
Provides REST API access to Zhilian OS neural system capabilities
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from ..services.neural_system import NeuralSystemOrchestrator
from ..services.federated_learning_service import federated_learning_service
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
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")
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
            top_k=request.top_k
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
            top_k=request.top_k
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
            top_k=request.top_k
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
        # In a real implementation, this would load the model from the path
        # For now, we'll use a placeholder
        local_model = {"weights": [], "bias": []}  # Placeholder

        success = await neural_system.participate_in_federated_learning(
            store_id=request.store_id,
            local_model=local_model,
            training_samples=request.training_samples
        )

        if success:
            return FederatedLearningParticipationResponse(
                success=True,
                round_number=neural_system.fl_service.current_round,
                message="Successfully participated in federated learning"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to participate in federated learning")
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
            total_stores=len(federated_learning_service.participating_stores),
            federated_learning_round=federated_learning_service.training_rounds,
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

