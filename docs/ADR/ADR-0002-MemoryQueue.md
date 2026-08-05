# ADR-0002: MemoryPriorityQueue

Status: Accepted

Date: 2026-08-05

Context

- AIOS-Core requires a transport abstraction for event buffering and delivery.
- The EventBus must remain backend-agnostic and depend on interfaces only.
- Early development needs a reliable, deterministic in-memory queue for local
  kernels, tests, and CI until distributed/durable adapters are available.

Problem

- We need a queue that provides priority ordering, FIFO semantics within the
  same priority, bounded capacity, backpressure semantics, and predictable
  behavior for testing and local operation.

Decision

- Implement `QueueInterface` as the canonical transport contract and provide
  `MemoryPriorityQueue` as the first concrete implementation.
- `MemoryPriorityQueue` is a heap-based priority queue that uses a supplied
  monotonic sequence number to achieve FIFO ordering within the same priority.
- EventBus (publication layer) assigns `QueueItem.sequence` to preserve
  ordering semantics; queues remain transport-agnostic and do not generate
  sequence numbers.

Alternatives considered

1. asyncio.Queue
   - Pros: Battle-tested, simple API, well integrated with asyncio.
   - Cons: No native priority support; would require wrapping/composition to
     achieve priority + FIFO behavior; less deterministic ordering for tests.

2. asyncio.PriorityQueue
   - Pros: Native priority ordering.
   - Cons: Does not guarantee FIFO for items with equal priority without
     additional sequence handling; still not as inspectable for metrics.

3. External broker (Redis, Kafka, RabbitMQ)
   - Pros: Persistence, distributed delivery, high durability and scalability.
   - Cons: Operational complexity, eventual consistency semantics, and added
     integration cost in early development; not suitable for unit tests or
     local kernels without additional infra.

Why MemoryPriorityQueue was selected

- Provides deterministic ordering (priority + FIFO) required for reliable
  unit tests and deterministic system behavior.
- Simple to implement and reason about; low risk for early development and
  foundational validation.
- Allows EventBus and other components to be developed against stable
  interfaces without committing to any specific distributed broker.

Consequences

Positive
- Deterministic ordering and simple semantics make testing and debugging
  predictable.
- Clean separation of interface and implementation allows future replacement
  without touching EventBus logic.

Negative
- MemoryPriorityQueue is single-process and non-persistent; not suitable for
  multi-node or durable message storage.
- Not a substitute for production-grade distributed brokers where required.

Migration path

- Implement RedisQueue using Redis Streams or Sorted Sets and mapping
  priority/sequence semantics.
- Implement KafkaQueue using partitions and timestamp/sequence ordering.
- Implement RabbitMQQueue using priorities or exchange/routing patterns.
- Each adapter must implement `QueueInterface` and pass the contract test
  suite located in tests/contracts/test_queue_contract.py.

