import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  matcher: [
    // Match all pathnames except API routes, Next internals, and static files.
    // API calls must bypass locale middleware so rewrites like /api/navigation/*
    // are not transformed into /en/api/navigation/*.
    "/((?!api|_next|_vercel|.*\\..*).*)",
  ],
};
