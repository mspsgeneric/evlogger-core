# event_sim.py
import asyncio, time, random, statistics as stats, argparse
from dataclasses import dataclass

# importa sua função real de tradução
from evtranslator.translate import google_web_translate

try:
    import aiohttp
except ImportError:
    raise SystemExit("Instale aiohttp: pip install aiohttp")

@dataclass
class Result:
    ok: bool
    latency: float
    err: str | None = None

def pct(values, p):
    if not values: return 0.0
    k = int(round((p/100)*(len(values)-1)))
    return sorted(values)[k]

async def translate_once(session, text, src, dst, timeout_s=8.0):
    # aplica timeout duro por chamada (igual ao modo-evento)
    return await asyncio.wait_for(
        google_web_translate(session, text, src, dst),
        timeout=timeout_s
    )

async def worker(name, queue, results, src, dst, timeout_s):
    async with aiohttp.ClientSession() as session:
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                return
            text = item
            t0 = time.perf_counter()
            try:
                _ = await translate_once(session, text, src, dst, timeout_s)
                dt = time.perf_counter() - t0
                results.append(Result(True, dt))
            except Exception as e:
                dt = time.perf_counter() - t0
                results.append(Result(False, dt, str(e)))
            finally:
                queue.task_done()

async def run_test(duration_s, target_rps, concurrency, src, dst, timeout_s):
    # pool de textos para simular conversas de vários usuários/canais
    text_pool = [
        "Olá, tudo bem?", "Mensagem de teste contínua.",
        "Falando rápido no evento, vamos ver se segura.",
        "Frase com emojis 😀🔥 e acentos.",
        "Outro texto para variar a carga.",
        "Mais uma linha para simulação.",
        "Tradução rodando em pico, medir latência!"
    ]

    queue = asyncio.Queue(maxsize=5000)
    results: list[Result] = []

    workers = [asyncio.create_task(worker(f"w{i}", queue, results, src, dst, timeout_s))
               for i in range(concurrency)]

    start = time.perf_counter()
    sent = 0

    # produtor com taxa-alvo de envio (RPS)
    while (time.perf_counter() - start) < duration_s:
        for _ in range(target_rps):
            await queue.put(random.choice(text_pool))
            sent += 1
        await asyncio.sleep(1.0)

    await queue.join()
    for _ in workers:
        await queue.put(None)
    await asyncio.gather(*workers)

    elapsed = time.perf_counter() - start
    total = len(results)
    ok = sum(1 for r in results if r.ok)
    errs = [r for r in results if not r.ok]
    lat_ok = [r.latency for r in results if r.ok]

    def fmt_ms(s): return f"{s*1000:.0f} ms"

    print("\n=== Simulado de Evento ===")
    print(f"Duração........: {duration_s}s")
    print(f"Oferta (RPS)...: {target_rps} req/s")
    print(f"Concorrência...: {concurrency}")
    print(f"Enviadas.......: {sent}")
    print(f"Concluídas.....: {total} (OK: {ok} | Erros: {len(errs)})")
    print(f"Throughput real: {total/elapsed:.1f} req/s")
    if lat_ok:
        print(f"p50: {fmt_ms(pct(lat_ok,50))} | p90: {fmt_ms(pct(lat_ok,90))} | "
              f"p95: {fmt_ms(pct(lat_ok,95))} | p99: {fmt_ms(pct(lat_ok,99))}")
        print(f"Média: {fmt_ms(stats.mean(lat_ok))}")
    if errs:
        kinds = {}
        for r in errs:
            key = ("429" if "429" in (r.err or "") else
                   "timeout" if "Timeout" in (r.err or "") or "asyncio.TimeoutError" in (r.err or "") else
                   "other")
            kinds[key] = kinds.get(key, 0) + 1
        print("Erros..........:", kinds)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=120, help="segundos de teste")
    ap.add_argument("--rps", type=int, default=20, help="requisições por segundo (oferta)")
    ap.add_argument("--conc", type=int, default=10, help="tarefas simultâneas")
    ap.add_argument("--src", default="auto")
    ap.add_argument("--dst", default="en")
    ap.add_argument("--timeout", type=float, default=8.0)
    args = ap.parse_args()
    asyncio.run(run_test(args.duration, args.rps, args.conc, args.src, args.dst, args.timeout))
