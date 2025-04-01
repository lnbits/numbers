import random
from datetime import datetime

import httpx
from lnbits.core.services import pay_invoice
from lnbits.core.views.api import api_lnurlscan

from .crud import (
    update_game,
    update_player,
    get_all_game_players
)
import requests
from datetime import datetime, timezone

async def get_pr(ln_address, amount):
    data = await api_lnurlscan(ln_address)
    if data.get("status") == "ERROR":
        return
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url=f"{data['callback']}?amount={amount* 1000}")
            if response.status_code != 200:
                return
            return response.json()["pr"]
    except Exception:
        return None

def get_latest_block():
    blocks = requests.get("https://mempool.space/api/blocks").json()
    return blocks[0]

def get_game_game_winner(block_hash: str, odds: int) -> int:
    tail_hex = block_hash[-4:]
    tail_decimal = int(tail_hex, 16)
    return tail_decimal % odds

# Protects against blocks taking longer than 25mins to be mined.
# In views_api we check if the game is closing within 30 minutes, and stop all bets.
# Between the two checks we have a 5 minute buffer.
async def calculate_winners(game):
    if (
        datetime.now().timestamp() > game.closing_date.timestamp()
        and not game.completed
    ):
        players = await get_all_game_players(game.id, game.height_number)
        if not players:
            game.completed = True
            await update_game(game)
            return
        block = get_latest_block()
        if not block:
            return
        if block["timestamp"] > game.closing_date.timestamp() or datetime.now(timezone.utc).timestamp() - block["timestamp"] > 25 * 60:
            return
        game.block_height = block["id"]
        game.height_number = get_game_game_winner(block["id"], game.odds)
        players = await get_all_game_players(game.id, game.height_number)
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
