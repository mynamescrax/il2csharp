using System;
using Demo;

static void Check(bool ok, string name)
{
    if (!ok) throw new Exception(name);
}

var board = new ScoreBoard();
board.SetScore(ScoreRules.StartingScore());
Check(board.ReadScore() == 10, "starting score");
board.SetScore(ScoreRules.AddBonus(board.ReadScore(), 90));
Check(board.score == 100 && ScoreRules.IsWinning(board.ReadScore()), "winning threshold");
Check(!ScoreRules.IsWinning(99) && !ScoreRules.IsWinning(-1), "below threshold");
foreach (int points in new[] { int.MinValue, -1, 0, 1, int.MaxValue })
    Check(ScoreRules.ClampAtZero(points) == Math.Max(0, points), "clamp: " + points);
Check(ScoreRules.DecodeNetworkScore(0x01020304) == 0x04030201, "byte order");
Check(ScoreRules.DecodeNetworkScore(0x80) == int.MinValue, "result sign bit");
Check(ScoreRules.DecodeNetworkScore(int.MinValue) == 0x80, "input sign bit");
var timer = new RoundTimer();
foreach (int seconds in new[] { 1, 0, -1 })
{
    timer.remaining = seconds;
    Check(timer.SecondsLeft() == seconds && timer.HasExpired() == (seconds <= 0), "timer");
}
Console.WriteLine("demo behavior OK");
