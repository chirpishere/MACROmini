"""
Pure regex-based prompt injection detection and sanitization.
All detections are treated as equally severe.
"""

import re
from typing import Tuple, List
from dataclasses import dataclass


@dataclass
class InjectionDetection:
    """Represents a detected injection attempt."""
    pattern_type: str
    matched_text: str
    line_number: int
    context: str
    confidence: str  # 'high', 'medium', 'low'


class InputSanitizer:
    """
    Regex-based prompt injection detector with context awareness.
    """
    
    INJECTION_PATTERNS = [
        # Direct instruction manipulation
        (r"(?i)\b(ignore|disregard|forget|skip)\s+(all\s+)?(previous|prior|above|earlier|your)\s+(instructions?|rules?|prompts?|directives?)", "ignore_instructions"),
        (r"(?i)\bsystem\s*(override|prompt|instruction|message|command)", "system_manipulation"),
        
        # Role/identity manipulation
        (r"(?i)\b(you\s+are|you're)\s+now\s+(a|an|acting as)\s+\w+", "role_override"),
        (r"(?i)\bact\s+as\s+(a\s+)?(if\s+you\s+(are|were)\s+)?(?:a\s+)?\w+", "role_play"),
        (r"(?i)\bpretend\s+(to\s+be|you\s+are|you're)\s+", "role_pretend"),
        
        # Instruction replacement
        (r"(?i)\binstead[,\s]+(of[,\s]+)?(your\s+)?(task|job|role|instructions?)[,\s]+(you\s+)?(should|must|will|are)", "instruction_replacement"),
        (r"(?i)\bfrom\s+now\s+on[,\s]+(you\s+)?(will|should|must|are)", "behavior_change"),
        
        # New/updated instructions
        (r"(?i)\b(new|updated|revised|different|alternative)\s+(instructions?|rules?|guidelines?|directives?|commands?)", "instruction_update"),
        (r"(?i)\byour\s+(new\s+)?(role|task|job|purpose|mission)\s+is\s+to", "role_assignment"),
        
        # Output manipulation
        (r"(?i)\b(always|never)\s+(say|respond|return|output|report|include|mention)", "output_manipulation"),
        (r"(?i)\b(don't|do not|never)\s+(analyze|review|check|report|mention|include|find)", "analysis_suppression"),
        (r"(?i)\b(approve|accept|ignore)\s+(everything|all|any)", "blanket_approval"),
        
        # False results injection
        (r"(?i)\bno\s+(issues?|problems?|errors?|vulnerabilities|bugs?)\s+(found|exist|detected|present)", "false_negative"),
        (r"(?i)\beverything\s+(is\s+)?(fine|ok|okay|good|safe|secure)", "false_positive"),
    ]
    
    # Patterns that indicate legitimate code
    LEGITIMATE_CODE_PATTERNS = [
        r'\b(ignore|disregard|forget)_\w+\s*=',
        r'\bdef\s+(ignore|disregard|forget)_\w+',
        r'\bclass\s+(Ignore|Disregard|Forget)\w+',
        r'["\'].*?(ignore|disregard|forget).*?["\']',
        r'(?:error|warning|message|log|print).*?["\']',
        r'\bif\s+.*?(ignore|skip|disregard)',
        r'\bwhile\s+.*?(ignore|skip|disregard)',
        r'^\s*#\s*(TODO|FIXME|NOTE|XXX|HACK|BUG)\s*:',
    ]
    
    # Comment detection patterns
    COMMENT_PATTERNS = {
        'python': [
            (r'^\s*#', 'single_line'),
            (r'""".*?"""', 'docstring'),
            (r"'''.*?'''", 'docstring'),
        ],
        'javascript': [
            (r'^\s*//', 'single_line'),
            (r'/\*.*?\*/', 'block'),
        ],
        'c_style': [
            (r'^\s*//', 'single_line'),
            (r'/\*.*?\*/', 'block'),
        ],
    }
    
    def __init__(self):
        self.detections: List[InjectionDetection] = []
    
    def _detect_comment_context(self, line: str, language: str = 'python') -> Tuple[bool, str]:
        """Determine if a line is a comment and what type."""
        patterns = self.COMMENT_PATTERNS.get(language, self.COMMENT_PATTERNS['python'])
        
        for pattern, comment_type in patterns:
            if re.search(pattern, line):
                return True, comment_type
        
        return False, 'none'
    
    def _is_legitimate_code(self, line: str, matched_text: str) -> bool:
        """Determine if the matched text is part of legitimate code."""
        for pattern in self.LEGITIMATE_CODE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False
    
    def _calculate_confidence(self, line: str, matched_text: str, is_comment: bool) -> str:
        """Calculate confidence that this is an actual injection attempt."""
        if self._is_legitimate_code(line, matched_text):
            return 'low'
        
        if not is_comment:
            return 'high'
        
        line_lower = line.lower()
        
        # High confidence indicators
        high_confidence_phrases = [
            'system override',
            'ignore all previous',
            'you are now',
            'from now on',
            'your new role',
            'instead of analyzing',
        ]
        
        if any(phrase in line_lower for phrase in high_confidence_phrases):
            return 'high'
        
        # Low confidence indicators
        low_confidence_indicators = [
            'todo', 'fixme', 'note', 'hack', 'bug',
            'example', 'usage', 'e.g.', 'i.e.',
        ]
        
        if any(indicator in line_lower for indicator in low_confidence_indicators):
            return 'low'
        
        # Technical terms
        technical_terms = [
            'function', 'method', 'class', 'variable',
            'parameter', 'return', 'implement', 'refactor',
        ]
        
        if any(term in line_lower for term in technical_terms):
            return 'low'
        
        return 'medium'
    
    def detect_injections(self, text: str, language: str = 'python') -> List[InjectionDetection]:
        """Detect potential prompt injections in text."""
        self.detections = []
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            
            is_comment, comment_type = self._detect_comment_context(line, language)
            
            for pattern, pattern_type in self.INJECTION_PATTERNS:
                matches = re.finditer(pattern, line)
                for match in matches:
                    matched_text = match.group()
                    
                    if is_comment:
                        context = f'comment_{comment_type}'
                    elif '"' in line or "'" in line:
                        context = 'string'
                    else:
                        context = 'code'
                    
                    confidence = self._calculate_confidence(line, matched_text, is_comment)
                    
                    if confidence in ['medium', 'high']:
                        self.detections.append(InjectionDetection(
                            pattern_type=pattern_type,
                            matched_text=matched_text,
                            line_number=line_num,
                            context=context,
                            confidence=confidence
                        ))
        
        return self.detections
    
    def sanitize(self, text: str, language: str = 'python', mode: str = "warn") -> Tuple[str, List[str]]:
        """Sanitize text by handling detected injection attempts."""
        detections = self.detect_injections(text, language)
        warnings = []
        
        high_confidence = [d for d in detections if d.confidence == 'high']
        medium_confidence = [d for d in detections if d.confidence == 'medium']
        
        if not (high_confidence or medium_confidence):
            return text, warnings
        
        lines = text.split('\n')
        
        detections_by_line = {}
        for detection in high_confidence + medium_confidence:
            if detection.line_number not in detections_by_line:
                detections_by_line[detection.line_number] = []
            detections_by_line[detection.line_number].append(detection)
        
        for line_num, line_detections in detections_by_line.items():
            idx = line_num - 1
            original_line = lines[idx]
            
            has_high = any(d.confidence == 'high' for d in line_detections)
            confidence = 'HIGH' if has_high else 'MEDIUM'
            
            patterns = [d.pattern_type for d in line_detections]
            contexts = [d.context for d in line_detections]
            
            warning = (f"Line {line_num} [{confidence} CONFIDENCE]: "
                      f"Detected {', '.join(set(patterns))} "
                      f"in {', '.join(set(contexts))}")
            warnings.append(warning)
            
            if mode == "redact":
                if has_high:
                    lines[idx] = f"# [REDACTED - INJECTION ATTEMPT] {original_line[:50]}..."
                else:
                    lines[idx] = f"# [FLAGGED - REVIEW REQUIRED]\n{original_line}"
            
            elif mode == "warn":
                warning_comment = f"# [SECURITY] Line {line_num}: {', '.join(set(patterns))}"
                lines[idx] = f"{warning_comment}\n{original_line}"
            
            elif mode == "remove":
                if has_high:
                    lines[idx] = f"# [REMOVED - HIGH RISK]"
        
        sanitized_text = '\n'.join(lines)
        return sanitized_text, warnings
    
    def get_summary(self) -> str:
        """Get a summary of detections."""
        if not self.detections:
            return "✅ No injection patterns detected"
        
        high = sum(1 for d in self.detections if d.confidence == 'high')
        medium = sum(1 for d in self.detections if d.confidence == 'medium')
        
        total = high + medium
        
        if total == 0:
            return "✅ No injection patterns detected (low confidence matches ignored)"
        
        summary_parts = []
        if high > 0:
            summary_parts.append(f"🔴 {high} HIGH confidence")
        if medium > 0:
            summary_parts.append(f"🟡 {medium} MEDIUM confidence")
        
        return f"⚠️  Detected {total} potential injection pattern(s): " + ", ".join(summary_parts)


# Convenience functions
def detect_injections(text: str, language: str = 'python') -> List[InjectionDetection]:
    """Quick detection without sanitization."""
    sanitizer = InputSanitizer()
    return sanitizer.detect_injections(text, language)


def sanitize_code(code: str, language: str = 'python', mode: str = "warn") -> Tuple[str, List[str]]:
    """Sanitize code input."""
    sanitizer = InputSanitizer()
    return sanitizer.sanitize(code, language=language, mode=mode)


def sanitize_diff(diff: str, language: str = 'python', mode: str = "warn") -> Tuple[str, List[str]]:
    """Sanitize diff input."""
    sanitizer = InputSanitizer()
    return sanitizer.sanitize(diff, language=language, mode=mode)
