# Simplification

## Description
A simplification removes avoidable scope, components, coordination, or cognitive load. It protects the essential result while making the path easier to complete and maintain. The suggestion should name what is removed instead of praising simplicity in the abstract. It should distinguish optional machinery from a requirement that downstream users rely on. A good simplification also notices what new limitation the reduction creates. The proposal is worthwhile when the saved effort or clarity exceeds the value of what is discarded.

## Things to consider
- What part of the current work is optional?
- Which essential value must remain intact?
- What dependency disappears with the reduction?
- Who could be affected by the removed scope?
- What new limitation or tradeoff appears?
- Can the change be reversed if the premise is wrong?
- How will the simpler result be verified?
- What future expansion should remain possible without building it now?
