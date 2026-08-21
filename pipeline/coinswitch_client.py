# DEPRECATED: Venue-specific legacy adapter retained only for audit. ADR-017
# selects Binance as the sole future venue. Do not configure or call this client.
"""
CoinSwitch Pro — Async API Client (HFT/DMA Edition)

All order operations (place, cancel, status, positions, leverage) route through
the HFT/DMA endpoint:  https://dma.coinswitch.co
which speaks the Bybit V5 REST API dialect.

Standard CoinSwitch endpoint (https://coinswitch.co) is kept only for:
  • Key validation      GET  /trade/api/v2/validate/keys
  • Server time         GET  /trade/api/v2/time
  • Futures wallet      GET  /trade/api/v2/futures/wallet_balance
  • Spot portfolio      GET  /trade/api/v2/user/portfolio

HFT/DMA endpoints used
──────────────────────
  POST /dma/api/v1/funds/transfer          fund / withdraw the sub-account
  POST /v5/position/set-leverage           set leverage (buyLeverage + sellLeverage)
  POST /v5/order/create                    place any order (Limit / Market / stop)
  POST /v5/order/cancel                    cancel one order by orderId
  POST /v5/order/cancel-all                cancel all open orders for a symbol
  GET  /v5/order/realtime                  active (open) orders; filterable by orderId
  GET  /v5/order/history                   filled / cancelled order history
  GET  /v5/position/list                   open positions
  GET  /v5/account/wallet-balance          HFT wallet USDT balance

Authentication (same as standard CoinSwitch)
  Algorithm : Ed25519
  Secret key: hex-encoded 32-byte Ed25519 private key (64 hex chars)
  Headers   : Content-Type, X-AUTH-APIKEY, X-AUTH-SIGNATURE, X-AUTH-EPOCH
  Message   :
    GET  → METHOD + unquote_plus(path?k=v&...) + epoch_ms
    POST → METHOD + path + epoch_ms   (body NOT signed)

Install:
  pip install cryptography aiohttp
"""

import json
import logging
import time
import urllib.parse
import uuid
from typing import Optional

import aiohttp
from cryptography.hazmat.primitives.asymmetric import ed25519

# Import all URL 
from pipeline.config_trader import (
    EXCHANGE,
    BASE_URL, 
    HFT_BASE_URL,
    EP_VALIDATE_KEYS,
    EP_SERVER_TIME,
    EP_SERVER_PING,
    EP_FUTURES_WALLET,
    EP_SPOT_PORTFOLIO,
    EP_HFT_FUND_TRANSFER,
    EP_HFT_SET_LEVERAGE,
    EP_HFT_ORDER_CREATE,
    EP_HFT_ORDER_CANCEL,
    EP_HFT_ORDER_CANCEL_ALL,
    EP_HFT_ORDER_REALTIME,
    EP_HFT_ORDER_HISTORY,
    EP_HFT_POSITION_LIST,
    EP_HFT_WALLET_BALANCE,
    EP_HFT_INSTRUMENTS_INFO
)




logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Symbol helpers
# ══════════════════════════════════════════════════════════════════════════════

def to_cs_symbol(sym_key: str) -> str:
    """
    Convert a pipeline sym_key to an HFT/DMA (Bybit V5-style) symbol.

    HFT uses USDT-settled perpetuals in UPPERCASE with no separators.

    Examples
    ────────
    'BTCUSDT'        → 'BTCUSDT'   (already correct)
    'BTC/USDT:USDT'  → 'BTCUSDT'   (ccxt perpetual format)
    'BTC/USDT'       → 'BTCUSDT'   (ccxt spot format)
    'XPIN/USDT'      → 'XPINUSDT'
    """
    sym = sym_key.upper()
    sym = sym.replace(":USDT", "")   # strip ccxt margin token
    sym = sym.replace("/", "")       # strip pair separator
    return sym


# ══════════════════════════════════════════════════════════════════════════════
# Signature  (validated against check.py)
# ══════════════════════════════════════════════════════════════════════════════

def _build_signature(
    secret_key_hex: str,
    method: str,
    path: str,
    params: Optional[dict] = None,
) -> tuple[str, str]:
    """
    Build Ed25519 signature.  Returns (epoch_ms_str, signature_hex).

    Message:
      GET  → METHOD + unquote_plus(path?k=v&k2=v2) + epoch_ms
      POST → METHOD + path + epoch_ms    (body excluded)
    """
    epoch_ms = str(int(time.time() * 1000))
    endpoint = path

    if method == "GET" and params:
        sep      = "&" if urllib.parse.urlparse(path).query else "?"
        endpoint = path + sep + urllib.parse.urlencode(params)
        endpoint = urllib.parse.unquote_plus(endpoint)

    message = method + endpoint + epoch_ms
    secret_bytes = bytes.fromhex(secret_key_hex)
    private_key  = ed25519.Ed25519PrivateKey.from_private_bytes(secret_bytes)
    sig_bytes    = private_key.sign(message.encode("utf-8"))
    return epoch_ms, sig_bytes.hex()


# ══════════════════════════════════════════════════════════════════════════════
# Client
# ══════════════════════════════════════════════════════════════════════════════

class CoinSwitchClient:
    """
    Async REST client — all order operations via HFT/DMA (Bybit V5 API).

    Usage (context manager — recommended):
        async with CoinSwitchClient(api_key, secret_key_hex) as cs:
            await cs.validate_keys()
            balance = await cs.get_hft_balance()
            ...

    Usage (manual):
        cs = CoinSwitchClient(api_key, secret_key_hex)
        ...
        await cs.close()
    """

    def __init__(self, api_key: str, secret_key_hex: str, timeout: float = 10.0):
        self._api_key        = api_key.strip()
        self._secret_key_hex = secret_key_hex.strip()
        self._timeout        = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── internal helpers ──────────────────────────────────────────────────────

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    def _auth_headers(self, method: str, path: str,
                      params: Optional[dict] = None) -> dict:
        epoch, sig = _build_signature(self._secret_key_hex, method, path, params)
        return {
            "Content-Type":     "application/json",
            "X-AUTH-APIKEY":    self._api_key,
            "X-AUTH-SIGNATURE": sig,
            "X-AUTH-EPOCH":     epoch,
        }

    async def _req(self, method: str, path: str,
                   payload: Optional[dict] = None,
                   params:  Optional[dict] = None) -> dict:
        """Authenticated request to the standard CoinSwitch base URL."""
        url        = BASE_URL + path
        sig_params = params if method == "GET" else None
        hdrs       = self._auth_headers(method, path, sig_params)
        sess       = await self._sess()
        try:
            async with sess.request(
                method, url,
                headers = hdrs,
                params  = params,
                json    = payload if method != "GET" else None,
            ) as resp:
                text = await resp.text()
                if resp.status not in (200, 201):
                    logger.error("[cs] %s %s → HTTP %d: %s",
                                 method, path, resp.status, text[:300])
                    return {"error": text, "http_status": resp.status}
                try:
                    return json.loads(text)
                except Exception:
                    return {"raw": text}
        except Exception as e:
            logger.error("[cs] %s %s exception: %s", method, path, e)
            return {"error": str(e)}

    async def _hft_req(self, method: str, path: str,
                       payload: Optional[dict] = None,
                       params:  Optional[dict] = None) -> dict:
        """
        Authenticated request to the HFT/DMA base URL.
        Same signature scheme as the standard API.
        """
        url        = HFT_BASE_URL + path
        sig_params = params if method == "GET" else None
        hdrs       = self._auth_headers(method, path, sig_params)
        sess       = await self._sess()
        try:
            async with sess.request(
                method, url,
                headers = hdrs,
                params  = params,
                json    = payload if method != "GET" else None,
            ) as resp:
                text = await resp.text()
                if resp.status not in (200, 201):
                    logger.error("[cs/hft] %s %s → HTTP %d: %s",
                                 method, path, resp.status, text[:300])
                    return {"error": text, "http_status": resp.status}
                try:
                    return json.loads(text)
                except Exception:
                    return {"raw": text}
        except Exception as e:
            logger.error("[cs/hft] %s %s exception: %s", method, path, e)
            return {"error": str(e)}

    # ══════════════════════════════════════════════════════════════════════════
    # Standard API — auth / utility (no order operations here)
    # ══════════════════════════════════════════════════════════════════════════

    async def validate_keys(self) -> dict:
        """GET /trade/api/v2/validate/keys — verify API credentials."""
        return await self._req("GET", EP_VALIDATE_KEYS)

    async def ping(self) -> dict:
        """GET /trade/api/v2/ping — connectivity check."""
        return await self._req("GET", EP_SERVER_PING)

    async def get_server_time(self) -> dict:
        """GET /trade/api/v2/time — server epoch (ms). No auth required."""
        sess = await self._sess()
        try:
            async with sess.get(
                BASE_URL + EP_SERVER_TIME,
                headers={"Content-Type": "application/json"},
            ) as resp:
                return json.loads(await resp.text())
        except Exception as e:
            return {"error": str(e)}

    # ══════════════════════════════════════════════════════════════════════════
    # Standard API — wallet / balance (fallback for account info)
    # ══════════════════════════════════════════════════════════════════════════

    async def get_futures_wallet(self) -> dict:
        """GET /trade/api/v2/futures/wallet_balance — standard futures wallet."""
        resp = await self._req("GET", EP_FUTURES_WALLET)
        data = resp.get("data")
        if isinstance(data, dict) and not resp.get("error"):
            logger.debug("[cs] RAW FUTURES WALLET: %s", json.dumps(resp, indent=2))
            return resp

        # Fallback: spot portfolio INR balance
        logger.warning(
            "[cs] Futures wallet endpoint unexpected response (%s) — "
            "falling back to spot portfolio.",
            resp.get("http_status", "?"),
        )
        portfolio = await self._req("GET", EP_SPOT_PORTFOLIO)
        logger.debug("[cs] RAW PORTFOLIO JSON: %s", json.dumps(portfolio, indent=2))

        if "data" in portfolio and isinstance(portfolio["data"], list):
            inr_balance = 0.0
            for asset in portfolio["data"]:
                if asset.get("name") == "Indian Rupee":
                    inr_balance = float(asset.get("main_balance", 0) or 0)
                    break
            return {
                "http_status": 200,
                "data": {
                    "availableBalance": inr_balance,
                    "totalBalance":     inr_balance,
                },
            }
        return portfolio

    async def get_portfolio(self) -> dict:
        """GET /trade/api/v2/user/portfolio — spot portfolio (all coin balances)."""
        return await self._req("GET", EP_SPOT_PORTFOLIO)

    # ══════════════════════════════════════════════════════════════════════════
    # HFT/DMA — account funding
    # ══════════════════════════════════════════════════════════════════════════

    async def initialize_hft_subaccount(self, amount: float = 1.0) -> dict:
        """
        Transfer funds IN to the HFT sub-account from the main wallet.
        Must be called at least once to initialize the sub-account.
        """
        payload = {
            "direction":     "IN",
            "amount":        amount,
            "client_txn_id": str(uuid.uuid4()),
        }
        logger.info("[cs/hft] Initialising sub-account | amount=%.4f USDT", amount)
        return await self._hft_req("POST", EP_HFT_FUND_TRANSFER, payload=payload)

    async def get_hft_balance(self) -> dict:
        """
        Response shape (Bybit V5):
          result.list[0].coin[i].walletBalance  / availableToWithdraw
        """
        params = {"accountType": "UNIFIED"}
        return await self._hft_req("GET", EP_HFT_WALLET_BALANCE, params=params)

    # ══════════════════════════════════════════════════════════════════════════
    # HFT/DMA — leverage
    # ══════════════════════════════════════════════════════════════════════════

    async def set_hft_leverage(self, symbol: str,
                               leverage: int = 10) -> dict:
        """
        buyLeverage and sellLeverage are sent as strings.
        """
        payload = {
            "category":     "linear",
            "symbol":        symbol.upper(),
            "buyLeverage":  str(leverage),
            "sellLeverage": str(leverage),
        }
        logger.info("[cs/hft] Set leverage %s → %dx", symbol, leverage)
        return await self._hft_req("POST", EP_HFT_SET_LEVERAGE, payload=payload)

    # ══════════════════════════════════════════════════════════════════════════
    # HFT/DMA — order placement
    # ══════════════════════════════════════════════════════════════════════════

    async def place_hft_order(
        self,
        symbol:            str,
        side:              str,             # "Buy" | "Sell"  (or "BUY"/"SELL" — normalised)
        order_type:        str  = "Limit",  # "Limit" | "Market"
        qty:               str  = "0",
        price:             Optional[str] = None,
        tif:               str  = "GTC",    # "GTC" | "IOC" | "PostOnly"
        position_idx:      int  = 0,        # 0 = one-way mode
        reduce_only:       bool = False,
        trigger_price:     Optional[str] = None,   # for stop / conditional orders
        trigger_by:        str  = "LastPrice",      # LastPrice | MarkPrice | IndexPrice
        trigger_direction: Optional[int] = None,   # 1 = rise above, 2 = fall below
        stop_order_type:   Optional[str] = None,   # "Stop" for stop-limit/stop-market
        order_link_id:     Optional[str] = None,   # client-assigned ID (optional)
    ) -> dict:
        """
        Order type guide
        ────────────────
        Limit entry       → order_type="Limit", price=entry_px
        Market close      → order_type="Market"
        TP limit          → order_type="Limit", price=tp_px, reduce_only=True
        SL stop-limit     → order_type="Limit", price=sl_limit_px,
                            trigger_price=sl_trigger_px, stop_order_type="Stop",
                            trigger_direction=2 (long SL) or 1 (short SL),
                            reduce_only=True
                            (sl_limit_px must be <= sl_trigger_px for a sell,
                             or >= sl_trigger_px for a buy, to guarantee fill)
        SL stop-market    → order_type="Market", trigger_price=sl_px,
                            stop_order_type="Stop", reduce_only=True
        """
        # Normalise side casing: accept BUY/SELL or Buy/Sell
        side = side.capitalize()   # "buy" → "Buy", "SELL" → "Sell"

        payload: dict = {
            "category":    "linear",
            "symbol":       symbol.upper(),
            "side":         side,
            "orderType":    order_type,
            "qty":          str(qty),
            "timeInForce":  "IOC" if order_type == "Market" else tif,
            "positionIdx":  position_idx,
            "reduceOnly":   reduce_only,
        }

        # price applies to Limit orders AND to stop-limit orders (order_type="Limit"
        # with trigger_price + stop_order_type="Stop")
        if price is not None:
            payload["price"] = str(price)

        if trigger_price is not None:
            payload["triggerPrice"]     = str(trigger_price)
            payload["triggerBy"]        = trigger_by
        if trigger_direction is not None:
            payload["triggerDirection"] = trigger_direction

        # stopOrderType = "Stop" is required for all conditional (stop) orders
        # on Bybit V5 — both stop-market and stop-limit
        if stop_order_type is not None:
            payload["stopOrderType"] = stop_order_type

        if order_link_id:
            payload["orderLinkId"] = order_link_id

        logger.info(
            "[cs/hft] ORDER %s %s %s qty=%s price=%s trigger=%s reduce=%s",
            side, order_type, symbol, qty, price, trigger_price, reduce_only,
        )
        return await self._hft_req("POST", EP_HFT_ORDER_CREATE, payload=payload)

    # ══════════════════════════════════════════════════════════════════════════
    # HFT/DMA — order cancellation
    # ══════════════════════════════════════════════════════════════════════════

    async def cancel_hft_order(
        self,
        symbol:        str,
        order_id:      Optional[str] = None,
        order_link_id: Optional[str] = None,
    ) -> dict:
        """
        Cancel one active HFT order by orderId or orderLinkId.
        At least one identifier must be supplied.
        """
        if not order_id and not order_link_id:
            return {"error": "Must provide order_id or order_link_id"}

        payload: dict = {
            "category": "linear",
            "symbol":    symbol.upper(),
        }
        if order_id:
            payload["orderId"] = order_id
        if order_link_id:
            payload["orderLinkId"] = order_link_id

        logger.info("[cs/hft] Cancel order %s", order_id or order_link_id)
        return await self._hft_req("POST", EP_HFT_ORDER_CANCEL, payload=payload)

    async def cancel_all_hft_orders(self, symbol: str) -> dict:
        """
        Cancel ALL active orders for a symbol at once.
        Equivalent to the standard API's cancel_all_orders().
        """
        payload = {
            "category": "linear",
            "symbol":    symbol.upper(),
        }
        logger.info("[cs/hft] Cancel ALL orders for %s", symbol)
        return await self._hft_req("POST", EP_HFT_ORDER_CANCEL_ALL, payload=payload)

    # ══════════════════════════════════════════════════════════════════════════
    # HFT/DMA — order status / history
    # ══════════════════════════════════════════════════════════════════════════

    async def get_hft_open_orders(self, symbol: str) -> list[dict]:
        """
        Returns all active (open / partially-filled) orders for a symbol.
        """
        params = {
            "category": "linear",
            "symbol":    symbol.upper(),
        }
        resp   = await self._hft_req("GET", EP_HFT_ORDER_REALTIME, params=params)
        orders = resp.get("result", {}).get("list", [])
        logger.info("[cs/hft] %d open order(s) for %s", len(orders), symbol)
        return orders

    async def get_hft_order(self, symbol: str, order_id: str) -> dict:
        """
        Fetch a single order by orderId.

        Strategy:
          1. Check order realtime  (active orders — New / PartiallyFilled)
          2. If not found, check /v5/order/history  (Filled / Cancelled)

        Returns the order dict on success, {} if not found.

        Bybit V5 order fields of interest:
          orderId       — exchange-assigned order ID
          orderStatus   — New | PartiallyFilled | Filled | Cancelled | Rejected | Deactivated
          avgPrice      — average fill price (populated once filled)
          qty           — original qty
          cumExecQty    — filled qty so far
        """
        params = {
            "category": "linear",
            "symbol":    symbol.upper(),
            "orderId":   order_id,
        }

        # Try active orders first (fast path)
        resp   = await self._hft_req("GET", EP_HFT_ORDER_REALTIME, params=params)
        orders = resp.get("result", {}).get("list", [])
        if orders:
            return orders[0]

        # Fall back to order history (filled / cancelled)
        resp   = await self._hft_req("GET", EP_HFT_ORDER_HISTORY, params=params)
        orders = resp.get("result", {}).get("list", [])
        if orders:
            return orders[0]

        logger.debug("[cs/hft] Order %s not found for %s", order_id, symbol)
        return {}

    # ══════════════════════════════════════════════════════════════════════════
    # HFT/DMA — positions
    # ══════════════════════════════════════════════════════════════════════════

    async def get_hft_positions(self, symbol: Optional[str] = None) -> list[dict]:
        """
        Returns open perpetual futures positions (Bybit V5 format).

        Useful position fields:
          symbol, side (Buy/Sell), size, avgPrice, unrealisedPnl, leverage
        """
        params: dict = {"category": "linear"}
        if symbol:
            params["symbol"] = symbol.upper()
        resp = await self._hft_req("GET", EP_HFT_POSITION_LIST, params=params)
        positions = resp.get("result", {}).get("list", [])
        logger.info("[cs/hft] %d position(s) returned", len(positions))
        return positions
    

    # ══════════════════════════════════════════════════════════════════════════

    async def get_hft_instrument_info(self, symbol: Optional[str] = None) -> dict:
        """
        Key fields per instrument (inside result.list[]):
          symbol, lotSizeFilter.qtyStep, lotSizeFilter.minOrderQty,
          priceFilter.tickSize
        """
        params: dict = {"category": "linear"}
        if symbol:
            params["symbol"] = symbol.upper()
        return await self._hft_req("GET", EP_HFT_INSTRUMENTS_INFO, params=params)
