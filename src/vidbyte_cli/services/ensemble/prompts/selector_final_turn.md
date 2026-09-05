<task>
{{task}}
</task>

<round number="{{round}}" surviving="{{surviving}}" keep="1">
This is the final round. {{surviving}} candidates are still alive and exactly one may survive.
The candidate you keep is the approach that will actually be implemented, and your `rationale`
and `cons` for it are the entire brief the implementing agent receives — it cannot see this
conversation, the other candidates, or who proposed what. Say what is to be done and what it
must be careful of, concretely enough to act on.
</round>

<candidates>
{{candidates}}
</candidates>

Return the round as the single JSON object described in your instructions, keeping exactly one
candidate.
