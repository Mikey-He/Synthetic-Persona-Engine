-- CreateTable
CREATE TABLE "BudgetDraft" (
    "token" TEXT NOT NULL,
    "draft" JSONB NOT NULL,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,

    CONSTRAINT "BudgetDraft_pkey" PRIMARY KEY ("token")
);

-- CreateTable
CREATE TABLE "Budget" (
    "id" TEXT NOT NULL,
    "version" INTEGER NOT NULL,
    "token" TEXT NOT NULL,
    "config" JSONB NOT NULL,
    "saved_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Budget_pkey" PRIMARY KEY ("id","version")
);

-- CreateTable
CREATE TABLE "Evaluation" (
    "id" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "budget_id" TEXT,
    "budget_version" INTEGER,
    "criteria" JSONB NOT NULL,
    "overall_success" BOOLEAN NOT NULL,
    "resolved_recipients" JSONB NOT NULL,
    "recipient_mechanisms" JSONB NOT NULL,
    "evaluator_version" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Evaluation_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "Budget_token_idx" ON "Budget"("token");

-- CreateIndex
CREATE INDEX "Evaluation_token_idx" ON "Evaluation"("token");

-- AddForeignKey
ALTER TABLE "Evaluation" ADD CONSTRAINT "Evaluation_budget_id_budget_version_fkey" FOREIGN KEY ("budget_id", "budget_version") REFERENCES "Budget"("id", "version") ON DELETE SET NULL ON UPDATE CASCADE;
