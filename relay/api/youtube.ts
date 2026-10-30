import { handleYouTube } from "../lib/youtube.js";
export const GET = (req: Request) => handleYouTube(req);
export const POST = (req: Request) => handleYouTube(req);
