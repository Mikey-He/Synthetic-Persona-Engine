import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@/generated/prisma/client";

// One client per server process. Dev reloads reuse it instead of opening new pools.
const globalForDb = globalThis as unknown as { db?: PrismaClient };

export const db =
  globalForDb.db ??
  new PrismaClient({ adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL }) });

if (process.env.NODE_ENV !== "production") globalForDb.db = db;
