import { handleTwitch } from "../lib/twitch.js";
export const POST = (req: Request) => handleTwitch(req);
export const GET = (req: Request) => handleTwitch(req);
