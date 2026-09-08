<task>
{{task}}
</task>

<round number="{{round}}" surviving="{{surviving}}" keep="{{target}}">
This is narrowing round {{round}}. {{surviving}} candidates are still alive and exactly
{{target}} may survive this round. Weigh the pros and cons of every candidate you keep, and
list every id you drop. State the common comparison basis, summarize the round, and include
evidence, uncertainty, and implementation guidance for every survivor.
</round>

<candidates>
{{candidates}}
</candidates>

Return the round as the single JSON object described in your instructions, keeping exactly
{{target}} candidates.
