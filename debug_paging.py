from src.collectors.kalshi_client import fetch_candlesticks

# KXRTPRIMATE-75 那个门槛，时间范围用你之前 F12 看到的
candles = fetch_candlesticks(
    "KXRTPRIMATE",
    "140d9e59-f3bc-46bd-8bc8-bcba26799b34",
    1766592000, 1768230000, 60
)
print(f"拉到 {len(candles)} 根")
for c in candles[:3]:
    print(c)
for c in candles[-3:]:
    print(c)