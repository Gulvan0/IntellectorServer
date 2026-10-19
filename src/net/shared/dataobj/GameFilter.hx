package net.shared.dataobj;

import net.shared.board.Situation;
import net.shared.Outcome;
import net.shared.utils.UnixTimestamp;
import net.shared.TimeControlType;
import net.shared.PieceColor;
import net.shared.utils.PlayerRef;

enum GameFilter 
{
    HasPlayers(refs:Array<PlayerRef>, color:Null<PieceColor>);
    TimeControlTypes(types:Array<TimeControlType>);
    Rated;
    StartTsFrame(min:Null<UnixTimestamp>, max:Null<UnixTimestamp>);
    Outcomes(outcomes:Array<Outcome>);
    StartingSituation(sit:Situation);
    LastSituation(sit:Situation);
    AnySituation(sit:Situation);
    MoveCntFrame(min:Null<Int>, max:Null<Int>);
    StartSecsFrame(min:Null<Int>, max:Null<Int>);
    IncrementSecsFrame(min:Null<Int>, max:Null<Int>);
    ExpectedSecsFrame(min:Null<Int>, max:Null<Int>, slope:Null<Float>);
}