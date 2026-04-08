from fastapi import APIRouter

router = APIRouter(prefix="/options", tags=["Options"])


@router.get("/")
async def get_options():
    """Get available skills and sports options for the platform."""
    return {
        "skills": ["Beginner", "Intermediate", "Advanced"],
        "sports": ["Football", "Basketball", "Tennis", "Volleyball", "Badminton", "Cricket"]
    }
