// Static site: prerender all routes. Per-day/runtime logic lives client-side and
// is guarded for SSR, so prerendering the shell is safe.
export const prerender = true;
export const trailingSlash = 'ignore';
