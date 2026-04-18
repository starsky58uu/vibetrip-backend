from fastapi import APIRouter

# 這個 router 會被 api_router.py 給 include 進去
router = APIRouter()

@router.get("/test")
def test_blindbox():
    return {
        "status": "success",
        "message": "盲盒系統測試成功！",
        "data": {
            "vibe": "想吃甜點",
            "recommendation": "冠軍咖啡與隱藏版達克瓦茲"
        }
    }