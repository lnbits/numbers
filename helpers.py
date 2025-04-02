from datetime import datetime, timezone

import httpx
from lnbits.core.services import pay_invoice
from lnbits.core.views.api import api_lnurlscan

from .crud import get_all_unpaid_players, update_game, update_player


async def get_pr(ln_address, amount):
    data = await api_lnurlscan(ln_address)
    if data.get("status") == "ERROR":
        return
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url=f"{data['callback']}?amount={int(amount)* 1000}"
            )
            if response.status_code != 200:
                return
            return response.json()["pr"]
    except Exception:
        return None


async def get_latest_block():
    async with httpx.AsyncClient() as client:
        blocks = await client.get("https://mempool.space/api/blocks").json()
        assert blocks.status_code == 200
        return blocks[0]
    return None


def get_game_game_winner(block_hash: str, odds: int) -> int:
    tail_hex = block_hash[-6:]
    tail_decimal = int(tail_hex, 16)
    return tail_decimal % odds


async def calculate_winners(game):
    if (
        datetime.now().timestamp() > game.closing_date.timestamp()
        and not game.completed
    ):
        players = await get_all_unpaid_players(game.id)
        if not players:
            game.completed = True
            await update_game(game)
            return
        block = await get_latest_block()
        if not block:
            return
        if datetime.now(timezone.utc).timestamp() > game.closing_date.timestamp():
            pass
        elif (
            block["timestamp"] > game.closing_date.timestamp()
            or datetime.now(timezone.utc).timestamp() - block["timestamp"] > 25 * 60
        ):
            return
        game.block_height = block["id"]
        game.height_number = get_game_game_winner(block["id"], game.odds)
        players = await get_all_unpaid_players(game.id)
        for player in players:
            max_sat = (player.buy_in * game.odds) * (game.haircut / 100)
            pr = await get_pr(player.ln_address, max_sat)
            try:
                await pay_invoice(
                    wallet_id=game.wallet,
                    payment_request=pr,
                    max_sat=max_sat,
                    description=f"({player.ln_address}) won the numbers {game.name}!",
                )
                player.paid = True
                await update_player(player)
            except Exception:
                player.paid = False
                player.owed = max_sat
                await update_player(player)
        game.completed = True
        await update_game(game)
    return
