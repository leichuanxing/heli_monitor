/** Keep text proportional while expanding the layout to the actual screen aspect ratio. */
export function fitWall(width:number,height:number){
 const safeWidth=Number.isFinite(width)?Math.max(0,width):0
 const safeHeight=Number.isFinite(height)?Math.max(0,height):0
 const scale=Math.min(safeWidth/1920,safeHeight/1080)
 return{scale,left:0,top:0,canvasWidth:scale?safeWidth/scale:1920,canvasHeight:scale?safeHeight/scale:1080}
}
