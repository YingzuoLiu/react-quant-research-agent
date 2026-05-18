rom typing import Any, Dict, List


def get_catalog() -> List[Dict[str, Any]]:
    return [descriptor.summary() for descriptor in _DESCRIPTORS]


def get_details(kind: str) -> Dict[str, Any]:
    descriptor = _by_kind().get(kind)
    if descriptor is None:
        return {"error": "Unknown kind: {0}".format(kind)}
    return descriptor.details()


class _StepDescriptor:
    def __init__(
        self,
        kind: str,
        purpose: str,
        required_fields: List[str],
        sample: Dict[str, Any],
        notes: List[str],
    ) -> None:
        self.kind = kind
        self.purpose = purpose
        self.required_fields = required_fields
        self.sample = sample
        self.notes = notes

    def summary(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "purpose": self.purpose,
            "required_fields": list(self.required_fields),
            "example_config": dict(self.sample),
        }

    def details(self) -> Dict[str, Any]:
        payload = self.summary()
        payload["notes"] = list(self.notes)
        return payload


def _by_kind() -> Dict[str, _StepDescriptor]:
    return {descriptor.kind: descriptor for descriptor in _DESCRIPTORS}


_DESCRIPTORS = [
    _StepDescriptor(
        kind="trigger.manual",
        purpose="Seed the draft with initial input values such as the symbol universe.",
        required_fields=[],
        sample={"universe": ["sh.600000", "sz.000001"]},
        notes=[
            "Usually the first step in a draft.",
            "Its output can be referenced later with $trigger_manual['field'].",
            "For example, $trigger_manual['universe'] can be passed into data.market_bars as symbols.",
        ],
    ),
    _StepDescriptor(
        kind="data.market_bars",
        purpose="Fetch grouped daily market bar series for one or more symbols.",
        required_fields=["symbols"],
        sample={
            "symbols": "$trigger_manual['universe']",
            "lookback_days": 5,
        },
        notes=[
            "This runtime step uses BaoStock for A-share symbols such as sh.600000 or sz.000001.",
            "The return value should be a mapping from symbol to a list of daily bars.",
            "Each bar should contain at least date and close price.",
            "Use lookback_days to control how many recent bars are needed.",
        ],
    ),
    _StepDescriptor(
        kind="factor.momentum",
        purpose="Compute momentum scores from grouped market bars.",
        required_fields=["bars"],
        sample={
            "bars": "$data_market_bars",
            "window": 3,
        },
        notes=[
            "This step expects grouped bars, not a single flat list of candles.",
            "The bars input usually comes from data.market_bars.",
            "A common config is bars=$data_market_bars and window=3.",
            "The output usually contains a scores field that can be passed into factor.rank.",
        ],
    ),
    _StepDescriptor(
        kind="factor.rank",
        purpose="Rank symbols by a score mapping such as momentum scores.",
        required_fields=["values"],
        sample={
            "values": "$factor_momentum['scores']",
            "descending": True,
        },
        notes=[
            "Use descending=True when higher scores should rank first.",
            "The values input usually comes from factor.momentum['scores'].",
            "The output usually contains ordered rows and top symbols.",
        ],
    ),
    _StepDescriptor(
        kind="research_chat",
        purpose="Generate a natural-language explanation for the research result.",
        required_fields=["prompt"],
        sample={
            "prompt": "Explain this momentum ranking: $factor_rank['ordered']"
        },
        notes=[
            "This runtime step calls a real chat-completions API.",
            "The prompt should explicitly include the upstream result to explain.",
            "Use it after factor.rank when the user asks for interpretation or explanation.",
            "The output contains generated text, usually under the content field.",
        ],
    ),
    _StepDescriptor(
        kind="output.report",
        purpose="Format the final research result into a structured report payload.",
        required_fields=["content"],
        sample={
            "content": "$research_chat['content']",
            "title": "Momentum Ranking Report",
        },
        notes=[
            "Usually the final step in a research workflow.",
            "Use this after research_chat when the workflow needs a clean final report output.",
            "The content field can reference research_chat['content'].",
            "This step is optional for simple drafts, but useful when a final report node is expected.",
        ],
    ),
]
