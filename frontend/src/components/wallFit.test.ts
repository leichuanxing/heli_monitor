import { expect, it } from 'vitest'
import { fitWall } from './wallFit'

it.each([[1920,1080,1],[2560,1440,4/3],[3840,2160,2]])('fits the complete canvas at %s × %s', (width,height,scale)=>{
 const result=fitWall(width,height)
 expect(result.scale).toBeCloseTo(scale)
 expect(result.left).toBeCloseTo(0)
 expect(result.top).toBeCloseTo(0)
 expect(1920*result.scale).toBeCloseTo(width)
 expect(1080*result.scale).toBeCloseTo(height)
})
it.each([[3440,1440],[1280,720],[1080,1920],[1366,768],[0,0]])('keeps all four canvas edges inside a %s × %s container',(width,height)=>{
 const result=fitWall(width,height)
 expect(result.left).toBeGreaterThanOrEqual(0)
 expect(result.top).toBeGreaterThanOrEqual(0)
 expect(result.left+1920*result.scale).toBeLessThanOrEqual(width+.00001)
 expect(result.top+1080*result.scale).toBeLessThanOrEqual(height+.00001)
})

it.each([[3440,1440],[1920,1200],[1600,1200],[5120,1440],[1080,1920]])('fills the entire %s × %s viewport without distorting text',(width,height)=>{
 const result=fitWall(width,height)
 expect(result.canvasWidth*result.scale).toBeCloseTo(width)
 expect(result.canvasHeight*result.scale).toBeCloseTo(height)
 expect(result.canvasWidth).toBeGreaterThanOrEqual(1920)
 expect(result.canvasHeight).toBeGreaterThanOrEqual(1080)
 expect(result.left).toBe(0)
 expect(result.top).toBe(0)
})
it.each([[0,0],[-100,200],[Infinity,1080],[1920,NaN]])('handles unavailable dimensions safely',(width,height)=>{
 const result=fitWall(width,height)
 expect(Number.isFinite(result.scale)).toBe(true)
 expect(Number.isFinite(result.canvasWidth)).toBe(true)
 expect(Number.isFinite(result.canvasHeight)).toBe(true)
 expect(result.scale).toBeGreaterThanOrEqual(0)
})
