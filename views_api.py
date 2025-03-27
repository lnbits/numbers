from datetime import datetime
from http import HTTPStatus

from fastapi import APIRouter, Depends
from lnbits.core.crud import get_user
from lnbits.core.models import WalletTypeInfo
from lnbits.core.services import create_invoice
from lnbits.decorators import require_admin_key
from loguru import logger
from starlette.exceptions import HTTPException

from .crud import (
    create_numbers,
    delete_numbers,
    get_numbers,
    get_numbers_by_user,
)
from .helpers import get_pr
from .models import CreateNumbers, Getgame, JoinNumbersGame

numbers_api_router = APIRouter()


@numbers_api_router.post("/api/v1/numbers", status_code=HTTPStatus.OK)
async def api_create_numbers(
    data: CreateNumbers, key_info: WalletTypeInfo = Depends(require_admin_key)
):
    if data.haircut < 0 or data.haircut > 50:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Haircut must be between 0 and 50",
        )
    numbers = await create_numbers(data, key_info.wallet.id, key_info.wallet.user)
    if not numbers:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Failed to create numbers"
        )
    return numbers


@numbers_api_router.get("/api/v1/numbers")
async def api_get_numbers(
    key_info: WalletTypeInfo = Depends(require_admin_key),
):
    user = await get_user(key_info.wallet.user)
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Failed to get user"
        )
    numbers = await get_numbers_by_user(user.id)
    return numbers


@numbers_api_router.post("/api/v1/numbers/join/", status_code=HTTPStatus.OK)
async def api_join_numbers(data: JoinNumbersGame):
    numbers_game = await get_numbers(data.numbers_id)
    logger.debug(numbers_game)
    if not numbers_game:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="No game found")
    if numbers_game.completed:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Game already ended"
        )
    pay_req = await get_pr(data.ln_address, numbers_game.buy_in)
    if not pay_req:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="lnaddress check failed"
        )
    payment = await create_invoice(
        wallet_id=numbers_game.wallet,
        amount=numbers_game.buy_in,
        memo=f"Numbers {numbers_game.name} for {data.ln_address}",
        extra={
            "tag": "numbers",
            "ln_address": data.ln_address,
            "numbers_id": data.numbers_id,
            "height_number": data.height_number,
        },
    )
    return {"payment_hash": payment.payment_hash, "payment_request": payment.bolt11}


@numbers_api_router.delete("/api/v1/numbers/{numbers_id}")
async def api_numbers_delete(
    numbers_id: str,
    key_info: WalletTypeInfo = Depends(require_admin_key),
):
    numbers = await get_numbers(numbers_id)
    if not numbers:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Pay link does not exist."
        )

    if numbers.wallet != key_info.wallet.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Not your pay link."
        )

    await delete_numbers(numbers_id)


@numbers_api_router.get(
    "/api/v1/numbers/numbers/{numbers_id}", status_code=HTTPStatus.OK
)
async def api_get_numbers(numbers_id: str):
    numbers = await get_numbers(numbers_id)
    if not numbers:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Numbers game does not exist."
        )
    if numbers.closing_date.timestamp() < datetime.now().timestamp():
        numbers.completed = True
    return Getgame(
        id=numbers.id,
        name=numbers.name,
        closing_date=numbers.closing_date,
        buy_in=numbers.buy_in,
        haircut=numbers.haircut,
        completed=numbers.completed,
    )
