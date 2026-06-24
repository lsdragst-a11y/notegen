import { IconButton } from "@/components/ui/IconButton";

<IconButton aria-label="Close">x</IconButton>;
// @ts-expect-error IconButton requires an accessible label.
<IconButton>x</IconButton>;
