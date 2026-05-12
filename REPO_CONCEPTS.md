# Repository Concepts

This document defines the shared language for the tree-walking and structural
rules architecture. It is the vocabulary companion to `PLAN.md`.

## Current Terms

`verbosity`
: Share of SLOC flagged as slop. It remains a union over flagged SLOC lines, so
overlapping signals count once.

`erosion`
: Share of function mass concentrated in high-complexity functions.

`SLOC`
: Real source lines of code. Comments, blank lines, and bare-string docstring
lines do not count.

`ast-grep rule`
: External YAML-backed rule run by the `sg` subprocess. ast-grep findings stay
separate from structural rule findings.

`structural rule`
: Python class in `src/scb_check/rules` that checks a typed subject from the
tree-walking IR and returns `RuleFinding | None`.

`source directive`
: Comment directive such as `# scbc ignore[...]` or `# scbc boundary`.
Directives belong with tree walking because they are parsed from source and
apply to source spans.

## Tree Walking

`tree_walking`
: Package that turns source text into language-agnostic IR, tracks SLOC and
source directives, dispatches language parsers, and builds semantic project
context.

`language parser`
: Parser implementation for one language. It accepts already-read source text
and returns a parsed file artifact. It does not walk the filesystem or read
files.

`language dispatch`
: Selection process that maps file extensions to candidate languages, applies
configured language filters, and tries candidate parsers until one succeeds.
Extensions may map to multiple languages.

`parsed file artifact`
: Internal wrapper containing pure `ModuleIR`, source text, and any parser-native
data needed by current clone detection. Parser-native data must not be exposed
through `ModuleIR` or to structural rules.

`ModuleIR`
: Pure Pydantic representation of a parsed source module. It contains generic
symbols, dependencies, source spans, SLOC lines, and top-level normalized code
facts. It does not contain raw tree-sitter nodes.

`SourceSpan`
: Reusable source location model with file, start line/column, and end
line/column. Every symbol, operation, value, directive, and finding should use
the same span model.

## Generic Code Model

`SymbolIR`
: Language-agnostic code entity such as module, class, function, method, or
value. Symbols have kind, name, qualified name, span, roles, signature, body,
and stored complexity where applicable.

`SymbolKind`
: Closed set describing what a symbol is, for example module, class, function,
method, or value. Rule runners use symbol kind to cut the search space before
calling rule checks.

`SymbolRole`
: Closed set of semantic roles assigned by parsing or enrichment, such as
contract member, inherited override, computed attribute, entrypoint, public API,
factory, or unknown external binding. Rules should ask about roles instead of
language-specific syntax like decorators.

`OperationIR`
: Normalized body operation such as return, bind, assign, call, branch, loop,
raise, yield, await, enter scope, or unknown. Operations are generic rather than
Python grammar nodes.

`ValueIR`
: Normalized value expression such as symbol reference, member access,
invocation, literal, collection, operator expression, or unknown.

`EffectIR`
: Derived behavior facts from operations and values, such as reads, writes,
mutations, project calls, external calls, allocation, raises, and unresolved
calls. Effects are derived after parsing because they depend on semantic
context.

`complexity`
: Stored cyclomatic and cognitive complexity values on function-like symbols.
The language parser computes these during parsing.

## Semantic Context

`ProjectIR`
: Project-level semantic model built from all parsed modules. It indexes modules,
symbols, ownership, imports, usages, inheritance edges, roles, and effects.

`RuleContext`
: Query interface passed to rules. It exposes language-agnostic semantic queries
over `ProjectIR` without requiring rules to understand parser-native syntax.

`local type facts`
: Conservative facts from annotations and local code, such as declared
annotations, immutable literal/container facts, `Final`-like bindings,
constructor member initialization, and resolvable class/protocol relationships.
The first cut does not implement a general type inference engine.

`required API surface`
: Symbol that exists because of a contract, inherited override, protocol,
computed attribute exposure, entrypoint, or external binding semantics. This is
a semantic concept, not a parser field like `has_decorator`.

## Rules

`Rule`
: Protocol satisfied by structural rule classes. Rule metadata is immutable
class metadata: `id`, `severity`, `languages`, and `target`.

`RuleTarget`
: Subject category a rule applies to, such as symbol, module, operation, or
project. The first cut implements symbol-targeted rules.

`RuleFinding`
: Fixed-field structural finding returned by a rule when it applies. It includes
rule ID, severity, message, span, subject name, and subject kind. Structural
findings are separate from ast-grep hits.

`rule namespace`
: One shared rule ID namespace across ast-grep and structural rules. Duplicate
IDs are invalid because `scbc ignore[...]` must never be ambiguous.

`TrivialWrapperRule`
: Structural rule that flags removable single-return wrappers. It is
opinionated: if a function-like symbol has no semantic reason to exist and its
return expression does not modify state or perform meaningful side effects, it
should be reported.

`keep reason`
: Semantic reason a trivial-looking symbol should not be removed. Examples
include required contract membership, inherited override, computed attribute
exposure, entrypoint behavior, external binding semantics, mutation, resource
management, validation, exception translation, logging, or metrics.

## Reporting

`structural finding LOC`
: SLOC covered by structural `RuleFinding` spans.

`structural finding count`
: Count of structural rule findings. The report should be generic rather than
adding one field per structural rule.

`clone finding`
: Duplicate syntax finding from current clone detection. Clone detection remains
separate and keeps its current parser-native implementation.

`ast-grep hit`
: Finding emitted by the ast-grep subprocess. ast-grep hits remain separate from
structural findings even though their rule IDs share the ignore namespace.
