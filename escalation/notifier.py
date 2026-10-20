import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, Optional
from escalation.handoff import EscalationReport


class EscalationNotifier:
    """
    Dispatches structured incident escalation memos to on-call communication channels:
    - Slack incoming webhooks (formatted Block Kit message)
    - Generic incident management webhooks (PagerDuty, Datadog, Opsgenie)
    - Persistent audit log file
    """

    def __init__(self, default_webhook_url: Optional[str] = None):
        self.default_webhook_url = default_webhook_url or os.getenv("ESCALATION_WEBHOOK_URL")

    def format_slack_payload(self, report: EscalationReport) -> Dict[str, Any]:
        """Formats the escalation report as a rich Slack Block Kit message."""
        severity_emoji = "🚨" if str(report.severity).upper() in ("CRITICAL", "HIGH") else "⚠️"
        
        attempted_text = ""
        if report.actions_attempted:
            lines = []
            for i, a in enumerate(report.actions_attempted, 1):
                icon = "✅" if a.get("success") else "❌"
                lines.append(f"{i}. {icon} `{a.get('action')}` on `{a.get('service')}`: {a.get('message')}")
            attempted_text = "\n".join(lines)
        else:
            attempted_text = "_None (action vetoed by deterministic guardrails or deemed unviable)._"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_emoji} SRE Escalation: {report.incident_id} [{report.target_service}]",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Target Service:*\n`{report.target_service}`"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{report.severity}"},
                    {"type": "mrkdwn", "text": f"*Confidence:*\n{report.confidence_score * 100:.1f}%"},
                    {"type": "mrkdwn", "text": f"*Escalated At:*\n{report.timestamp}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Escalation Reason:*\n> {report.escalation_reason}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Root Cause Hypothesis:*\n{report.diagnosed_hypothesis}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Mutations Attempted:*\n{attempted_text}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Recommended Next Step for Human SRE:*\n👉 {report.recommended_human_action}",
                },
            },
        ]

        return {
            "text": f"{severity_emoji} SRE Incident Escalation: {report.incident_id} ({report.target_service})",
            "blocks": blocks,
        }

    def dispatch_to_slack(self, report: EscalationReport, webhook_url: Optional[str] = None) -> bool:
        """Sends the report to a Slack incoming webhook endpoint."""
        url = webhook_url or self.default_webhook_url
        if not url:
            return False

        payload = self.format_slack_payload(report)
        return self._send_http_post(url, payload)

    def dispatch_to_generic_webhook(self, report: EscalationReport, webhook_url: Optional[str] = None) -> bool:
        """Sends the structured JSON report to any webhook endpoint."""
        url = webhook_url or self.default_webhook_url
        if not url:
            return False

        payload = report.model_dump()
        return self._send_http_post(url, payload)

    def save_to_audit_file(self, report: EscalationReport, filepath: str = "escalations_audit.log") -> str:
        """Appends the formatted markdown memo to a local persistent audit file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*70}\n")
            f.write(f"ESCALATION LOGGED AT: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*70}\n")
            f.write(report.to_markdown())
            f.write("\n\n")
        return os.path.abspath(filepath)

    def dispatch(
        self,
        report: EscalationReport,
        channel: str = "console",
        webhook_url: Optional[str] = None,
        audit_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Unified dispatch method."""
        results = {"channel": channel, "success": True, "details": []}

        # 1. Always append to audit log if specified
        if audit_file:
            path = self.save_to_audit_file(report, audit_file)
            results["details"].append(f"Saved to audit log: {path}")

        # 2. Webhook dispatch
        target_url = webhook_url or self.default_webhook_url
        if channel == "slack" and target_url:
            ok = self.dispatch_to_slack(report, target_url)
            results["success"] = ok
            results["details"].append("Dispatched to Slack webhook" if ok else "Failed to dispatch to Slack webhook")
        elif channel == "webhook" and target_url:
            ok = self.dispatch_to_generic_webhook(report, target_url)
            results["success"] = ok
            results["details"].append("Dispatched to HTTP webhook" if ok else "Failed to dispatch to HTTP webhook")
        else:
            # Console display
            results["details"].append("Rendered to console output")

        return results

    def _send_http_post(self, url: str, data: Dict[str, Any], timeout: float = 5.0) -> bool:
        """Lightweight HTTP POST using standard urllib with timeout."""
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return 200 <= resp.status < 300
        except Exception as e:
            print(f"[EscalationNotifier] Webhook delivery failed: {e}")
            return False
