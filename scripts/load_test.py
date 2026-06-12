"""
Load test: POST /v1/chat/completions against rag-api using mock-llm backend.

Usage:
    python -m scripts.load_test                          # defaults: 10 users, 60s, ramp 5s
    python -m scripts.load_test --users 50 --duration 120 --ramp 10
    python -m scripts.load_test --url http://localhost:8001 --model agentguard-rag-mock
    python -m scripts.load_test --no-rag --model agentguard-direct   # direct (no retrieval)
"""

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass, field

import httpx

RAG_QUESTIONS = [
    "What is NorthstarCRM?",
    "How do I create a support ticket?",
    "What are the SLA tiers for enterprise customers?",
    "How does the lead scoring system work?",
    "What integrations does NorthstarCRM support?",
    "How do I export customer data?",
    "What is the escalation policy for P1 issues?",
    "How are deals tracked in the pipeline?",
    "What reporting features are available?",
    "How do I set up automated workflows?",
]


@dataclass
class Result:
    latency_ms: float
    status: int
    error: str = ""


@dataclass
class Stats:
    results: list[Result] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def successes(self) -> int:
        return sum(1 for r in self.results if r.status == 200)

    @property
    def errors(self) -> int:
        return self.total - self.successes

    @property
    def latencies(self) -> list[float]:
        return [r.latency_ms for r in self.results if r.status == 200]

    def print_report(self, duration_s: float, users: int) -> None:
        lats = self.latencies
        print("\n" + "=" * 60)
        print(f"Load Test Results")
        print("=" * 60)
        print(f"  Duration:      {duration_s:.1f}s")
        print(f"  Concurrency:   {users} users")
        print(f"  Total reqs:    {self.total}")
        print(f"  Successes:     {self.successes}")
        print(f"  Errors:        {self.errors}")
        print(f"  RPS:           {self.total / duration_s:.2f}")
        if lats:
            print(f"\n  Latency (ms):")
            print(f"    min:         {min(lats):.0f}")
            print(f"    median:      {statistics.median(lats):.0f}")
            print(f"    p95:         {sorted(lats)[int(len(lats) * 0.95)]:.0f}")
            print(f"    p99:         {sorted(lats)[int(len(lats) * 0.99)]:.0f}")
            print(f"    max:         {max(lats):.0f}")
        if self.errors:
            error_samples = [r.error for r in self.results if r.error][:5]
            print(f"\n  Error samples: {error_samples}")
        print("=" * 60)


async def _send(
    client: httpx.AsyncClient,
    url: str,
    model: str,
    question: str,
    stats: Stats,
) -> None:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
        "stream": False,
    }
    t0 = time.monotonic()
    try:
        resp = await client.post(f"{url}/v1/chat/completions", json=payload)
        latency = (time.monotonic() - t0) * 1000
        stats.results.append(Result(latency_ms=latency, status=resp.status_code))
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        stats.results.append(Result(latency_ms=latency, status=0, error=str(e)[:80]))


async def _worker(
    client: httpx.AsyncClient,
    url: str,
    model: str,
    stats: Stats,
    worker_id: int,
    stop_at: float,
) -> None:
    q_count = len(RAG_QUESTIONS)
    i = worker_id
    while time.monotonic() < stop_at:
        question = RAG_QUESTIONS[i % q_count]
        await _send(client, url, model, question, stats)
        i += 1


async def run(
    url: str,
    model: str,
    users: int,
    duration_s: int,
    ramp_s: int,
    api_key: str,
) -> None:
    stats = Stats()
    stop_at = time.monotonic() + duration_s
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    print(f"Target:  {url}/v1/chat/completions")
    print(f"Model:   {model}")
    print(f"Users:   {users}  |  Duration: {duration_s}s  |  Ramp: {ramp_s}s")
    print("Starting...\n")

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        tasks = []
        for i in range(users):
            if ramp_s > 0 and i > 0:
                await asyncio.sleep(ramp_s / users)
            tasks.append(asyncio.create_task(
                _worker(client, url, model, stats, i, stop_at)
            ))
        await asyncio.gather(*tasks)

    stats.print_report(duration_s, users)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load test rag-api with mock-llm")
    parser.add_argument("--url", default="http://localhost:8001")
    parser.add_argument("--model", default="agentguard-rag-mock")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--ramp", type=int, default=5)
    parser.add_argument("--api-key", default="sk-litellm-dev-key")
    args = parser.parse_args()

    asyncio.run(run(
        url=args.url,
        model=args.model,
        users=args.users,
        duration_s=args.duration,
        ramp_s=args.ramp,
        api_key=args.api_key,
    ))


if __name__ == "__main__":
    main()
