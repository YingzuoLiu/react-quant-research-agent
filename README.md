# ReAct Quant Research Agent

A ReAct-style quantitative research agent capable of:

- Workflow planning
- Market data retrieval
- Momentum factor analysis
- Ranking generation
- Natural-language research explanation

The system follows a layered Agent architecture with:

- Planner layer
- Runtime execution layer
- Pipeline validation layer

---

## Architecture

```
User Request
    ↓
Planner
    ↓
Workflow Construction
    ↓
Runtime Execution
    ↓
Factor Computation
    ↓
Ranking
    ↓
Research Explanation
```

---

## Key Components

### Runtime Market Data Step

Implements grouped market-bar retrieval using BaoStock for A-share symbols.

### Planner Catalog

Provides planner-visible workflow descriptors for:

- Market data retrieval
- Factor computation
- Ranking
- Explanation generation

### Pipeline Validation

Validates:

- Unique step IDs
- Graph connectivity
- Required workflow nodes

### ReAct Loop Runtime

Supports:

- Iterative tool execution
- Repair prompts
- Idle detection
- Workflow export

---

## Example Workflow

```
trigger.manual
    ↓
data.market_bars
    ↓
factor.momentum
    ↓
factor.rank
    ↓
research_chat
```

---

## Design Notes

The project explores:

- Tool-driven workflow planning
- Structured Agent execution
- Pipeline validation
- Quantitative research automation