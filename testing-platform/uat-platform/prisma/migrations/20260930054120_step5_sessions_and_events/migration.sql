/*
  Warnings:

  - You are about to drop the column `token` on the `Budget` table. All the data in the column will be lost.
  - The primary key for the `BudgetDraft` table will be changed. If it partially fails, the table could be left without primary key constraint.
  - You are about to drop the column `token` on the `BudgetDraft` table. All the data in the column will be lost.
  - You are about to drop the column `token` on the `Evaluation` table. All the data in the column will be lost.
  - Added the required column `session_id` to the `Budget` table without a default value. This is not possible if the table is not empty.
  - Added the required column `session_id` to the `BudgetDraft` table without a default value. This is not possible if the table is not empty.
  - Added the required column `session_id` to the `Evaluation` table without a default value. This is not possible if the table is not empty.

*/
-- CreateEnum
CREATE TYPE "ActorType" AS ENUM ('human', 'synthetic');

-- CreateEnum
CREATE TYPE "Variant" AS ENUM ('A', 'B');

-- CreateEnum
CREATE TYPE "DatasetLabel" AS ENUM ('pilot', 'calibration_A', 'evaluation_A', 'evaluation_B', 'synthetic');

-- CreateEnum
CREATE TYPE "FamiliarityBand" AS ENUM ('low', 'medium', 'high');

-- CreateEnum
CREATE TYPE "TerminationReason" AS ENUM ('completion_declared', 'abandoned', 'step_limit', 'time_limit', 'loop', 'technical_error');

-- DropIndex
DROP INDEX "Budget_token_idx";

-- DropIndex
DROP INDEX "Evaluation_token_idx";

-- AlterTable
ALTER TABLE "Budget" DROP COLUMN "token",
ADD COLUMN     "session_id" TEXT NOT NULL;

-- AlterTable
ALTER TABLE "BudgetDraft" DROP CONSTRAINT "BudgetDraft_pkey",
DROP COLUMN "token",
ADD COLUMN     "session_id" TEXT NOT NULL,
ADD CONSTRAINT "BudgetDraft_pkey" PRIMARY KEY ("session_id");

-- AlterTable
ALTER TABLE "Evaluation" DROP COLUMN "token",
ADD COLUMN     "session_id" TEXT NOT NULL;

-- CreateTable
CREATE TABLE "Participant" (
    "id" TEXT NOT NULL,
    "familiarity_band" "FamiliarityBand" NOT NULL,
    "screening" JSONB,
    "consented_at" TIMESTAMPTZ(3),
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Participant_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Session" (
    "id" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "actor_type" "ActorType" NOT NULL,
    "participant_id" TEXT,
    "agent_run_id" TEXT,
    "variant" "Variant" NOT NULL,
    "dataset_label" "DatasetLabel" NOT NULL,
    "fixture_version" TEXT NOT NULL,
    "defaults_version" TEXT NOT NULL,
    "task_version" TEXT NOT NULL,
    "build_version" TEXT NOT NULL,
    "evaluator_version" TEXT NOT NULL,
    "reference_capture_id" TEXT,
    "viewport" JSONB,
    "zoom" DOUBLE PRECISION,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "started_at" TIMESTAMPTZ(3),
    "ended_at" TIMESTAMPTZ(3),
    "termination_reason" "TerminationReason",

    CONSTRAINT "Session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Event" (
    "id" SERIAL NOT NULL,
    "session_id" TEXT NOT NULL,
    "seq" INTEGER NOT NULL,
    "client_ts" TIMESTAMPTZ(3) NOT NULL,
    "server_ts" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "type" TEXT NOT NULL,
    "target" TEXT,
    "payload" JSONB,
    "screenshot_ref" TEXT,

    CONSTRAINT "Event_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AgentRun" (
    "id" TEXT NOT NULL,
    "model_id" TEXT NOT NULL,
    "prompt_version" TEXT NOT NULL,
    "persona_id" TEXT NOT NULL,
    "calibration_id" TEXT,
    "temperature" DOUBLE PRECISION,
    "started_at" TIMESTAMPTZ(3),

    CONSTRAINT "AgentRun_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AgentStep" (
    "id" SERIAL NOT NULL,
    "session_id" TEXT NOT NULL,
    "step_no" INTEGER NOT NULL,
    "screenshot_path" TEXT,
    "action" JSONB NOT NULL,
    "reason" TEXT,
    "executed" BOOLEAN NOT NULL,
    "error_label" TEXT,
    "latency_ms" INTEGER,

    CONSTRAINT "AgentStep_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SurveyResponse" (
    "id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "instrument" TEXT NOT NULL,
    "answers" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "SurveyResponse_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FixtureVersion" (
    "id" TEXT NOT NULL,
    "content" JSONB NOT NULL,
    "content_hash" TEXT NOT NULL,
    "frozen_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "FixtureVersion_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Session_token_key" ON "Session"("token");

-- CreateIndex
CREATE INDEX "Event_session_id_seq_idx" ON "Event"("session_id", "seq");

-- CreateIndex
CREATE INDEX "AgentStep_session_id_step_no_idx" ON "AgentStep"("session_id", "step_no");

-- CreateIndex
CREATE UNIQUE INDEX "SurveyResponse_session_id_instrument_key" ON "SurveyResponse"("session_id", "instrument");

-- CreateIndex
CREATE INDEX "Budget_session_id_idx" ON "Budget"("session_id");

-- CreateIndex
CREATE INDEX "Evaluation_session_id_idx" ON "Evaluation"("session_id");

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_participant_id_fkey" FOREIGN KEY ("participant_id") REFERENCES "Participant"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_agent_run_id_fkey" FOREIGN KEY ("agent_run_id") REFERENCES "AgentRun"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_fixture_version_fkey" FOREIGN KEY ("fixture_version") REFERENCES "FixtureVersion"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_defaults_version_fkey" FOREIGN KEY ("defaults_version") REFERENCES "FixtureVersion"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "BudgetDraft" ADD CONSTRAINT "BudgetDraft_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "Session"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Budget" ADD CONSTRAINT "Budget_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "Session"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Event" ADD CONSTRAINT "Event_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "Session"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AgentStep" ADD CONSTRAINT "AgentStep_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "Session"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Evaluation" ADD CONSTRAINT "Evaluation_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "Session"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SurveyResponse" ADD CONSTRAINT "SurveyResponse_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "Session"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
