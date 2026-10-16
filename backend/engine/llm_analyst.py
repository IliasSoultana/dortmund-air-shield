"""LLM Security Analyst CoPilot layer (MockAnalyst default + UniAnalyst /v1/responses).

The LLM is strictly an ANALYST, never a detector: it consumes structured verdicts
and 4D telemetry evidence from the deterministic detectors and produces plain-German
explanations, actionable countermeasure commands, and operator issue tickets.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

VALID_COMMANDS: tuple[str, ...] = (
    "SET_PROTECTION",
    "SAFE_RETURN_HOME",
    "RTH",
    "MOVE_ZONE",
    "CONFIRM_THREAT",
    "SET_JAMMING",
    "SET_SPOOFING",
    "FORCE_NODE_FAILURE",
    "RESET",
)

VALID_SEVERITIES: tuple[str, ...] = ("LOW", "MED", "CRIT")


def _dominant_dims(dims: dict[str, float]) -> list[str]:
    ordered = sorted(dims.items(), key=lambda kv: float(kv[1]), reverse=True)
    return [k for k, v in ordered if float(v) >= 1.5] or [ordered[0][0]] if ordered else ["snr"]


class MockAnalyst:
    """Deterministic template-based security analyst keyed on verdict label and deviating dims.

    Always available offline and bit-identical for fixed inputs.
    """

    backend_name: str = "MOCK"

    def analyze(
        self,
        verdict: dict[str, Any],
        evidence_window: list[Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        dev = str(verdict.get("device") or "DR-01")
        label = str(verdict.get("label") or "NOMINAL")
        sim = float(verdict.get("similarity") or 0.0)
        z_score = float(verdict.get("z_score") or 0.0)
        dims = dict(verdict.get("dims") or {})
        ev = list(verdict.get("evidence") or [-65.0, 34.0, 0.005, 1.1])
        rssi = float(ev[0]) if len(ev) > 0 else -65.0
        snr = float(ev[1]) if len(ev) > 1 else 34.0
        loss = float(ev[2]) if len(ev) > 2 else 0.005
        gnss = float(ev[3]) if len(ev) > 3 else 1.1
        win_len = len(evidence_window) if evidence_window is not None else 1
        dom = _dominant_dims(dims)
        dom_str = ", ".join(dom)

        if label == "NOMINAL":
            return {
                "backend": self.backend_name,
                "device": dev,
                "summary": (
                    f"Knoten {dev} operiert innerhalb des gelernten Nominal-Prototyps "
                    f"(SNR {snr:.1f} dB, RSSI {rssi:.1f} dBm, Paketverlust {loss * 100:.1f}%). "
                    f"Optische FSOC-Verbindung und GNSS-Stützung sind konsistent über {win_len} Messfenster."
                ),
                "hypothesis": "NOMINAL",
                "confidence": 0.98,
                "recommended_actions": [
                    {"command": "SET_PROTECTION", "label": "Hybriden DECT NR+ Schutz aktiv halten"},
                ],
                "issue": {
                    "title": f"[{dev}] Telemetrie im Nominalbereich (z={z_score:.1f})",
                    "severity": "LOW",
                    "assignee_role": "Mesh Telemetry Operator",
                },
            }

        if label == "UNEXPLAINED":
            return {
                "backend": self.backend_name,
                "device": dev,
                "summary": (
                    f"Auffällige 4D-Signatur auf {dev} entdeckt (z={z_score:.1f} in [{dom_str}], "
                    f"SNR {snr:.1f} dB, GNSS-Offset {gnss:.1f} m). "
                    f"Kein bekannter Bedrohungs-Prototyp erreicht die Kosinus-Schwelle (max. Ähnlichkeit {sim:.2f}). "
                    f"Bitte Profil bestätigen und DECT NR+ Fallback prüfen."
                ),
                "hypothesis": "unbekanntes Muster",
                "confidence": round(max(0.35, min(0.84, sim if sim > 0 else 0.62)), 2),
                "recommended_actions": [
                    {"command": "CONFIRM_THREAT", "label": "Signatur als neuen Bedrohungs-Prototyp speichern"},
                    {"command": "SET_PROTECTION", "label": "DECT NR+ Fallback & INS-Lock erzwingen"},
                    {"command": "SAFE_RETURN_HOME", "label": "Sicherheits-RTH vorbereiten"},
                ],
                "issue": {
                    "title": f"[{dev}] Unbekanntes Angriffsmuster ({dom_str}, z={z_score:.1f})",
                    "severity": "CRIT",
                    "assignee_role": "RF & Threat Intelligence Lead",
                },
            }

        if label == "jamming":
            return {
                "backend": self.backend_name,
                "device": dev,
                "summary": (
                    f"Breitband-Störsender auf {dev} identifiziert (Kosinus-Ähnlichkeit {sim:.2f}, "
                    f"SNR eingebrochen auf {snr:.1f} dB bei RSSI {rssi:.1f} dBm). "
                    f"Der Mesh-Knoten schaltet automatisch von FSOC-Laser auf das gebäudedurchdringende "
                    f"1,9 GHz DECT NR+ Band um und drosselt Video zugunsten von C2."
                ),
                "hypothesis": "jamming",
                "confidence": round(max(0.85, min(0.99, sim)), 2),
                "recommended_actions": [
                    {"command": "SET_PROTECTION", "label": "Band-Fallback auf DECT NR+ sichern"},
                    {"command": "MOVE_ZONE", "label": "Störzone Sektor West neu zentrieren"},
                    {"command": "SAFE_RETURN_HOME", "label": "Safe Return Home (RTH) auslösen"},
                ],
                "issue": {
                    "title": f"[{dev}] RF/Optisches Jamming erkannt (SNR {snr:.1f} dB)",
                    "severity": "CRIT",
                    "assignee_role": "Spectrum Defense Engineer",
                },
            }

        if label == "spoofing":
            return {
                "backend": self.backend_name,
                "device": dev,
                "summary": (
                    f"GNSS-L1-Spoofing auf {dev} bestätigt (Kosinus-Ähnlichkeit {sim:.2f}, "
                    f"Positionsdrift Δ={gnss:.1f} m gegenüber INS/VIO). "
                    f"Die Plausibilitätsprüfung verwirft den gefälschten Satelliten-Fix und hält die Drohne "
                    f"per Trägheitsnavigation auf dem realen Orbit."
                ),
                "hypothesis": "spoofing",
                "confidence": round(max(0.85, min(0.99, sim)), 2),
                "recommended_actions": [
                    {"command": "SET_PROTECTION", "label": "INS-Plausibilitäts-Sperre aktivieren"},
                    {"command": "SAFE_RETURN_HOME", "label": "Flotte per INS nach HQ zurückführen (RTH)"},
                ],
                "issue": {
                    "title": f"[{dev}] GNSS-Spoofing Abweichung Δ={gnss:.1f}m",
                    "severity": "MED" if gnss < 60.0 else "CRIT",
                    "assignee_role": "Navigation & GNC Specialist",
                },
            }

        # Learned custom / coordinated / carrier_blackout profiles
        _ = ctx
        return {
            "backend": self.backend_name,
            "device": dev,
            "summary": (
                f"Wiedererkanntes Bedrohungsprofil '{label}' auf {dev} "
                f"(Kosinus-Ähnlichkeit {sim:.2f}, z={z_score:.1f} in [{dom_str}]). "
                f"Durch das zuvor vom Operator bestätigte Prototyp-Lernen wurde das Muster sofort "
                f"klassifiziert (SNR {snr:.1f} dB, Verlust {loss * 100:.1f}%, GNSS Δ={gnss:.1f} m)."
            ),
            "hypothesis": label,
            "confidence": round(max(0.84, min(0.99, sim)), 2),
            "recommended_actions": [
                {"command": "SET_PROTECTION", "label": "DECT NR+ & INS-Schutzprofil durchsetzen"},
                {"command": "SAFE_RETURN_HOME", "label": "Notfall-RTH für Sektor einleiten"},
            ],
            "issue": {
                "title": f"[{dev}] Bestätigtes Bedrohungsprofil '{label}' aktiv",
                "severity": "CRIT",
                "assignee_role": "Incident Commander",
            },
        }


class UniAnalyst:
    """Opt-in university LLM analyst calling /v1/responses on chat.kiconnect.nrw.

    NOTE: gpt-6-studierende rejects reasoning_effort + tools on /v1/chat/completions
    with HTTP 400; this client uses /v1/responses exclusively and validates strict
    JSON output, falling back to MockAnalyst on any network or schema error.
    """

    backend_name: str = "UNI"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 15.0,
        fallback: MockAnalyst | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("LLM_BASE_URL")
            or "http://chat.kiconnect.nrw/v1"
        ).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL") or "gpt-6-studierende"
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "uni-hackathon"
        self.timeout_s = timeout_s
        self.fallback = fallback or MockAnalyst()

    def _build_prompt(
        self,
        verdict: dict[str, Any],
        evidence_window: list[Any] | None,
        context: dict[str, Any] | None,
    ) -> str:
        payload = {
            "verdict": verdict,
            "evidence_window_tail": (evidence_window or [])[-4:],
            "context": context or {},
            "allowed_commands": list(VALID_COMMANDS),
        }
        return (
            "Du bist der KI-Sicherheitsanalyst für Dortmund Air Shield (Drohnen-Mesh FSOC/DECT NR+). "
            "Analysiere das folgende deterministische Detektor-Urteil und antworte AUSSCHLIESSLICH mit "
            "einem validen JSON-Objekt mit genau diesen Schlüsseln: "
            "summary (2-3 Sätze auf Deutsch), hypothesis (String: Label oder 'unbekanntes Muster'), "
            "confidence (Zahl 0..1), recommended_actions (Liste von {command, label}, wobei command "
            f"einer von {list(VALID_COMMANDS)} sein MUSS), issue ({{title, severity: LOW|MED|CRIT, assignee_role}}).\n\n"
            f"Eingabedaten:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    def _extract_text(self, resp_json: dict[str, Any]) -> str:
        if isinstance(resp_json.get("output_text"), str) and resp_json["output_text"].strip():
            return resp_json["output_text"].strip()
        for item in resp_json.get("output", []) or []:
            if isinstance(item, dict):
                for content in item.get("content", []) or []:
                    if isinstance(content, dict) and isinstance(content.get("text"), str):
                        return content["text"].strip()
        choices = resp_json.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message", {})
            if isinstance(msg.get("content"), str):
                return msg["content"].strip()
        raise ValueError("No text content found in /v1/responses payload")

    def _validate_and_normalize(self, parsed: dict[str, Any], dev: str) -> dict[str, Any]:
        summary = str(parsed.get("summary") or "").strip()
        if not summary:
            raise ValueError("Missing summary in LLM JSON")
        hypothesis = str(parsed.get("hypothesis") or "unbekanntes Muster").strip()
        confidence = float(parsed.get("confidence", 0.75))
        confidence = max(0.0, min(1.0, confidence))

        raw_actions = parsed.get("recommended_actions")
        if not isinstance(raw_actions, list) or not raw_actions:
            raise ValueError("recommended_actions must be a non-empty list")
        actions: list[dict[str, str]] = []
        for act in raw_actions[:4]:
            if not isinstance(act, dict):
                continue
            cmd = str(act.get("command") or "").strip().upper()
            lbl = str(act.get("label") or cmd).strip()
            if cmd in VALID_COMMANDS:
                actions.append({"command": cmd, "label": lbl})
        if not actions:
            raise ValueError("No valid engine commands in recommended_actions")

        raw_issue = parsed.get("issue")
        if not isinstance(raw_issue, dict):
            raise ValueError("Missing issue object")
        sev = str(raw_issue.get("severity") or "MED").upper()
        if sev not in VALID_SEVERITIES:
            sev = "MED"
        issue = {
            "title": str(raw_issue.get("title") or f"[{dev}] Sicherheitsereignis ({hypothesis})"),
            "severity": sev,
            "assignee_role": str(raw_issue.get("assignee_role") or "Mesh Security Operator"),
        }

        return {
            "backend": self.backend_name,
            "device": dev,
            "summary": summary,
            "hypothesis": hypothesis,
            "confidence": round(confidence, 2),
            "recommended_actions": actions,
            "issue": issue,
        }

    def analyze(
        self,
        verdict: dict[str, Any],
        evidence_window: list[Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dev = str(verdict.get("device") or "DR-01")
        url = f"{self.base_url}/responses"
        prompt = self._build_prompt(verdict, evidence_window, context)
        body = json.dumps({
            "model": self.model,
            "input": prompt,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw_bytes = resp.read()
            resp_json = json.loads(raw_bytes.decode("utf-8"))
            txt = self._extract_text(resp_json)
            if txt.startswith("```"):
                txt = txt.strip("`")
                if txt.startswith("json"):
                    txt = txt[4:].strip()
            parsed = json.loads(txt)
            return self._validate_and_normalize(parsed, dev)
        except Exception as exc:
            logger.warning("UniAnalyst fallback to MockAnalyst (%s): %s", url, exc)
            return self.fallback.analyze(verdict, evidence_window, context)


class LLMAnalyst:
    """Facade selecting MockAnalyst (default) or UniAnalyst via LLM_ANALYST / LLS_ANALYST env var."""

    def __init__(
        self,
        mode: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        env_mode = (
            mode
            or os.environ.get("LLM_ANALYST")
            or os.environ.get("LLS_ANALYST")
            or "mock"
        ).strip().lower()
        self.mode = "uni" if env_mode == "uni" else "mock"
        self.mock_backend = MockAnalyst()
        self.uni_backend = UniAnalyst(
            base_url=base_url,
            timeout_s=timeout_s,
            fallback=self.mock_backend,
        )

    @property
    def active_backend_name(self) -> str:
        return "UNI" if self.mode == "uni" else "MOCK"

    def analyze(
        self,
        verdict: dict[str, Any],
        evidence_window: list[Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.mode == "uni":
            return self.uni_backend.analyze(verdict, evidence_window, context)
        return self.mock_backend.analyze(verdict, evidence_window, context)
